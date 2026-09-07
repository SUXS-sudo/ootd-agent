import asyncio, base64, html, ipaddress, json, re, socket, uuid
import httpx
from pathlib import Path
from datetime import timedelta
from .time_utils import datetime
from urllib.parse import urljoin, urlparse
from fastapi import APIRouter,Depends,File,Form,HTTPException,Query,Request,Response,UploadFile
from fastapi.responses import FileResponse,RedirectResponse,StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .config import settings
from .models import AuthSession,User,UserProfile,WardrobeItem,ImageAsset,WardrobeRelation,Outfit,OutfitFeedback,WearHistory,ImageTask,DeletionRequest,PhotoAsset,WeeklyPlan,PlanDay,NotificationPreference,AuthorizedIntegration,ProactiveEvent,AccessLog,ContextProfile,BehaviorFeature,RecommendationEvidence,StylingSession,RecommendationDecision,CandidateImpression,DecisionOutcome,RankingModel,PreferenceDriftEvent,PolicyAssignment
from .schemas import LocalAuthIn,ProfileIn,WardrobeItemIn,WardrobeItemOut,UploadSignIn,UploadCompleteIn,OutfitRequest,OutfitResponse,FeedbackIn,ReplaceOutfitItemIn,PhotoAnalysis,AdvancedPhotoAnalysis,WeeklyPlanRequest,WeeklyPlanResult,ReplanRequest,WardrobeGraphResult,TravelPlanRequest,TravelPlanResult,MultiSceneRequest,MultiSceneResult,StyleIdentityResult,ProactiveEventIn,NotificationPreferencesIn,PurchaseCandidate,PurchaseResult,TryOnRequest,BehaviorSignalIn
from .ranking import COLOR_FAMILIES,filter_items,generate_candidates,deterministic_results,required_item_terms,required_full_look_color,resolve_request_context
from .agent import rank_with_model
from .personalization import learn_from_feedback,build_style_identity,context_key,feedback_affinities
from .preference_cache import cache_styling_session,context_preferences,invalidate_preferences,recommendation_profile
from .graph import rebuild_graph
from .planning import create_weekly_plan,replan_dates,create_travel_plan,create_multiscene_plan
from .purchase import analyze_purchase,long_term_plan
from .proactive import connect_integration,ingest_event,scan_due_events,record_access
from .tryon import generate_clean_garment,generate_tryon,tryon_task_payload
from .intent import candidate_satisfies_handoff,merge_conversation_context,prefilter_items_by_handoff,understand_outfit_request
from .answer_guard import build_evidence_pack,guard_outfit_answer
from .photo_analysis import analyze_outfit_image
from .wardrobe_status import UNAVAILABLE_WARDROBE_STATUSES, WardrobeStatus
from .auth import bind_current_user,current_user_id,create_local_session,decode_token,hash_password,verify_password,issue_token,_stable_user_id
from .wardrobe_analysis import analyze_outfit_items, analyze_wardrobe_image
from .external_integrations import encrypt_credentials,exchange_outlook_code,open_meteo_weather,outlook_authorization_url,outlook_events,read_oauth_state
from .outfit_workflow import OutfitWorkflowError, run_outfit_agent
from .decisioning import candidate_features,counterfactual,detect_preference_drift,latest_model,outcome_reward,train_and_evaluate,update_thompson
from .object_storage import create_read_url,create_upload_url,local_path,object_metadata,probe_object,put_bytes,sha256_bytes

router=APIRouter(prefix="/api/v1",dependencies=[Depends(bind_current_user)])
def uid(): return current_user_id()

@router.get("/health")
def health(): return {"status":"ok","service":"ootd-api"}
def _auth_response(response:Response,user:User,db:Session):
    access,refresh=create_local_session(db,user)
    response.set_cookie("ootd_access",access,max_age=900,httponly=True,samesite="lax",secure=settings.environment=="production",path="/")
    response.set_cookie("ootd_refresh",refresh,max_age=30*24*3600,httponly=True,samesite="lax",secure=settings.environment=="production",path="/api/v1/auth")
    return {"access_token":access,"expires_in":900,"user":{"user_id":user.id,"email":user.email}}
@router.post("/auth/register",status_code=201)
def register(body:LocalAuthIn,response:Response,db:Session=Depends(get_db)):
    email=body.email.strip().lower()
    if "@" not in email:raise HTTPException(422,"请输入有效邮箱")
    if db.scalar(select(User).where(User.email==email)):raise HTTPException(409,"该邮箱已经注册")
    password_hash,password_salt=hash_password(body.password);user=User(id=_stable_user_id(email),email=email,password_hash=password_hash,password_salt=password_salt)
    db.add(user);db.add(UserProfile(user_id=user.id));db.commit();db.refresh(user);return _auth_response(response,user,db)
@router.post("/auth/login")
def login(body:LocalAuthIn,response:Response,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.strip().lower()))
    if not user or not user.password_hash or not user.password_salt or not verify_password(body.password,user.password_hash,user.password_salt):raise HTTPException(401,"邮箱或密码错误")
    return _auth_response(response,user,db)
@router.post("/auth/refresh")
def refresh(request:Request,response:Response,db:Session=Depends(get_db)):
    token=request.cookies.get("ootd_refresh")
    if not token:raise HTTPException(401,"登录已过期")
    payload=decode_token(token,"refresh");session=db.get(AuthSession,payload.get("sid"));user=db.scalar(select(User).where(User.email==payload["email"]))
    if not session or session.revoked_at or session.expires_at<datetime.utcnow() or not user or session.user_id!=user.id:raise HTTPException(401,"登录已过期")
    access=issue_token(user.email,"access",900);response.set_cookie("ootd_access",access,max_age=900,httponly=True,samesite="lax",secure=settings.environment=="production",path="/")
    return {"access_token":access,"expires_in":900,"user":{"user_id":user.id,"email":user.email}}
@router.post("/auth/logout",status_code=204)
def logout(request:Request,response:Response,db:Session=Depends(get_db)):
    token=request.cookies.get("ootd_refresh")
    if token:
        try:
            payload=decode_token(token,"refresh");session=db.get(AuthSession,payload.get("sid"))
            if session:session.revoked_at=datetime.utcnow();db.commit()
        except HTTPException:pass
    response.delete_cookie("ootd_refresh",path="/api/v1/auth");response.delete_cookie("ootd_access",path="/");response.status_code=204;return None
@router.get("/auth/me")
def auth_me(db:Session=Depends(get_db)):
    user=db.get(User,uid());return {"user_id":user.id,"email":user.email}
@router.get("/profile")
def profile(db:Session=Depends(get_db)): return db.get(UserProfile,uid())
@router.put("/profile")
def update_profile(body:ProfileIn,db:Session=Depends(get_db)):
    row=db.get(UserProfile,uid()) or UserProfile(user_id=uid());
    for k,v in body.model_dump().items(): setattr(row,k,v)
    db.add(row);db.commit();db.refresh(row);invalidate_preferences(uid());return row
@router.get("/wardrobe",response_model=list[WardrobeItemOut])
def wardrobe(status:str|None=None,db:Session=Depends(get_db)):
    q=select(WardrobeItem).where(WardrobeItem.user_id==uid()); q=q.where(WardrobeItem.clean_status==status) if status else q; return list(db.scalars(q))
@router.get("/wardrobe/insights-v2")
def insights_v2(db:Session=Depends(get_db)):
    graph=rebuild_graph(db,uid());items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==uid())));return {"most_worn_item_ids":[x.id for x in sorted(items,key=lambda x:x.wear_count,reverse=True)[:5]],"idle_item_ids":[x.id for x in items if x.wear_count<4],"core_item_ids":graph.core_item_ids,"isolated_item_ids":graph.isolated_item_ids,"functional_gaps":long_term_plan(db,uid())["functional_gaps"],"color_distribution":{c:sum(c in x.colors for x in items) for c in {c for x in items for c in x.colors}}}
@router.get("/wardrobe/{item_id}",response_model=WardrobeItemOut)
def wardrobe_item(item_id:str,db:Session=Depends(get_db)):
    row=db.get(WardrobeItem,item_id)
    if not row or row.user_id!=uid(): raise HTTPException(404,"item not found")
    return row
@router.post("/wardrobe",response_model=WardrobeItemOut,status_code=201)
def add_item(body:WardrobeItemIn,db:Session=Depends(get_db)):
    row=WardrobeItem(id=f"item_{uuid.uuid4().hex[:8]}",user_id=uid(),wear_count=0,**body.model_dump());db.add(row);db.commit();db.refresh(row);return row
@router.put("/wardrobe/{item_id}",response_model=WardrobeItemOut)
def update_wardrobe_item(item_id:str,body:WardrobeItemIn,db:Session=Depends(get_db)):
    row=db.get(WardrobeItem,item_id)
    if not row or row.user_id!=uid(): raise HTTPException(404,"item not found")
    for key,value in body.model_dump().items(): setattr(row,key,value)
    db.commit();db.refresh(row);return row
@router.delete("/wardrobe/{item_id}",status_code=204)
def delete_wardrobe_item(item_id:str,db:Session=Depends(get_db)):
    row=db.get(WardrobeItem,item_id)
    if not row or row.user_id!=uid():raise HTTPException(404,"衣物不存在")
    image_path=None
    if row.image_url and row.image_url.startswith("/generated/wardrobe-"):
        candidate=(Path(__file__).resolve().parents[1]/row.image_url.lstrip("/")).resolve()
        generated=(Path(__file__).resolve().parents[1]/"generated").resolve()
        if candidate.parent==generated:image_path=candidate
    relations=list(db.scalars(select(WardrobeRelation).where(WardrobeRelation.user_id==uid()).where((WardrobeRelation.source_item_id==item_id)|(WardrobeRelation.target_item_id==item_id))))
    for relation in relations:db.delete(relation)
    asset=db.get(ImageAsset,row.image_asset_id) if row.image_asset_id else None
    if asset and asset.user_id==uid():asset.status="pending_delete";asset.deleted_at=datetime.utcnow()
    db.delete(row);db.commit()
    if asset and settings.environment!="test":
        try:
            from .tasks import delete_asset
            delete_asset.apply_async(args=[asset.id],countdown=settings.storage_delete_grace_seconds)
        except Exception:
            pass
    if image_path:
        try:image_path.unlink(missing_ok=True)
        except OSError:pass
    return Response(status_code=204)
@router.post("/wardrobe/analyze")
async def analyze_wardrobe_upload(file:UploadFile=File(...)):
    if not (file.content_type or "").startswith("image/"):raise HTTPException(415,"仅支持图片文件")
    content=await file.read()
    if not content or len(content)>12*1024*1024:raise HTTPException(422,"图片为空或超过 12MB")
    try:return analyze_wardrobe_image(content,file.filename or "")
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
@router.post("/wardrobe/analyze-outfit")
async def analyze_outfit_for_wardrobe(file:UploadFile=File(...)):
    if not (file.content_type or "").startswith("image/"):raise HTTPException(415,"仅支持图片文件")
    content=await file.read()
    if not content or len(content)>12*1024*1024:raise HTTPException(422,"图片为空或超过 12MB")
    try:return await analyze_outfit_items(content,file.filename or "")
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
def _safe_public_url(value:str)->str:
    parsed=urlparse(value.strip())
    if parsed.scheme not in {"http","https"} or not parsed.hostname:raise HTTPException(422,"请输入有效的 http(s) 商品链接")
    try:
        addresses={row[4][0] for row in socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:raise HTTPException(422,"无法解析商品链接域名") from exc
    if any(ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback or ipaddress.ip_address(address).is_link_local or ipaddress.ip_address(address).is_reserved for address in addresses):raise HTTPException(422,"不支持内网或本机链接")
    return value.strip()
async def _fetch_public(client:httpx.AsyncClient,url:str)->httpx.Response:
    current=_safe_public_url(url)
    for _ in range(4):
        response=await client.get(current,headers={"User-Agent":"Mozilla/5.0 OOTD wardrobe importer"})
        if response.status_code not in {301,302,303,307,308}:response.raise_for_status();return response
        location=response.headers.get("location")
        if not location:break
        current=_safe_public_url(urljoin(current,location))
    raise HTTPException(422,"商品链接重定向次数过多")
@router.post("/wardrobe/import-link")
async def import_wardrobe_link(url:str=Form(...)):
    try:
        async with httpx.AsyncClient(timeout=12,follow_redirects=False) as client:
            page=await _fetch_public(client,url)
            content_type=page.headers.get("content-type","").lower();title="网购单品"
            if content_type.startswith("image/"):
                image_content=page.content;image_type=content_type.split(";",1)[0]
            else:
                source=page.text[:2_000_000]
                title_match=re.search(r"<title[^>]*>(.*?)</title>",source,re.I|re.S)
                if title_match:title=re.sub(r"\s+"," ",html.unescape(title_match.group(1))).strip()[:80]
                patterns=[r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']']
                image_match=next((match for pattern in patterns if (match:=re.search(pattern,source,re.I))),None)
                if not image_match:raise HTTPException(422,"未找到商品主图，请改用商品截图导入")
                image_response=await _fetch_public(client,urljoin(str(page.url),html.unescape(image_match.group(1))))
                image_content=image_response.content;image_type=image_response.headers.get("content-type","image/jpeg").split(";",1)[0]
            if not image_type.startswith("image/"):raise HTTPException(422,"商品主图格式无效，请改用截图导入")
            if not image_content or len(image_content)>12*1024*1024:raise HTTPException(422,"商品主图为空或超过 12MB")
            extension={"image/png":"png","image/webp":"webp"}.get(image_type,"jpg")
            filename=f"{title}.{extension}"
            suggestion=analyze_wardrobe_image(image_content,filename)
            return {"filename":filename,"mime_type":image_type,"image_data":base64.b64encode(image_content).decode(),"suggestion":suggestion,"source_url":url}
    except HTTPException:raise
    except (httpx.HTTPError,ValueError) as exc:raise HTTPException(422,"商品链接读取失败，请改用商品截图导入") from exc
@router.post("/wardrobe/render-clean")
async def render_clean_wardrobe_item(file:UploadFile=File(...),name:str=Form(...),category:str=Form(...),color:str=Form(...)):
    if not (file.content_type or "").startswith("image/"):raise HTTPException(415,"仅支持图片文件")
    return await generate_clean_garment(file,name,category,color)
@router.patch("/wardrobe/{item_id}/status")
def status(item_id:str,value:WardrobeStatus=Query(...),db:Session=Depends(get_db)):
    row=db.get(WardrobeItem,item_id)
    if not row or row.user_id!=uid(): raise HTTPException(404,"item not found")
    old=row.clean_status;row.clean_status=value;replanned=[]
    if value in UNAVAILABLE_WARDROBE_STATUSES:
        candidates=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==uid(),WardrobeItem.category==row.category,WardrobeItem.clean_status=="可穿",WardrobeItem.id!=row.id).order_by(WardrobeItem.formality_level.desc())))
        replacement=candidates[0].id if candidates else None
        for plan in db.scalars(select(WeeklyPlan).where(WeeklyPlan.user_id==uid(),WeeklyPlan.status=="active")):
            for day in db.scalars(select(PlanDay).where(PlanDay.plan_id==plan.id)):
                if row.id in day.item_ids:
                    day.item_ids=[replacement if x==row.id and replacement else x for x in day.item_ids if x!=row.id or replacement];day.affected_by=[f"status:{row.id}:{old}->{value}"];replanned.append(day.date)
    db.commit();return {"item_id":item_id,"status":value,"equivalent_replanned_dates":replanned}
@router.post("/uploads/sign")
def sign_upload(body:UploadSignIn,db:Session=Depends(get_db)):
    if not body.content_type.startswith("image/"):raise HTTPException(415,"仅支持图片文件")
    suffix=Path(body.filename).suffix.lower();suffix=suffix if suffix in {".jpg",".jpeg",".png",".webp"} else ".jpg"
    asset_id=f"asset_{uuid.uuid4().hex}";key=f"users/{uid()}/{body.kind}/{asset_id}/original{suffix}"
    asset=ImageAsset(id=asset_id,user_id=uid(),kind=body.kind,storage_backend=settings.storage_backend,bucket=settings.storage_bucket if settings.storage_backend!="local" else None,object_key=key,original_filename=Path(body.filename).name[:255],content_type=body.content_type,byte_size=body.byte_size,variants={},status="pending")
    db.add(asset);db.commit()
    upload_url=create_upload_url(asset_id,key,body.content_type)
    return {"asset_id":asset_id,"object_key":key,"upload_url":upload_url,"expires_in":settings.storage_upload_url_ttl_seconds,"headers":{"Content-Type":body.content_type}}

@router.put("/uploads/direct/{asset_id}",status_code=204)
async def direct_upload(asset_id:str,request:Request,db:Session=Depends(get_db)):
    asset=db.get(ImageAsset,asset_id)
    if not asset or asset.user_id!=uid() or asset.storage_backend!="local" or asset.status!="pending":raise HTTPException(404,"上传任务不存在")
    content=await request.body()
    if not content or len(content)>settings.storage_max_image_bytes or len(content)!=asset.byte_size:raise HTTPException(422,"图片大小与签名申请不一致")
    if request.headers.get("content-type","").split(";",1)[0]!=asset.content_type:raise HTTPException(415,"图片类型与签名申请不一致")
    put_bytes(asset.object_key,content,asset.content_type);asset.sha256=sha256_bytes(content);db.commit();return Response(status_code=204)

@router.post("/wardrobe/from-upload",response_model=WardrobeItemOut,status_code=201)
def create_wardrobe_from_upload(body:UploadCompleteIn,db:Session=Depends(get_db)):
    asset=db.scalar(select(ImageAsset).where(ImageAsset.id==body.asset_id).with_for_update())
    if not asset or asset.user_id!=uid() or asset.kind!="wardrobe":raise HTTPException(404,"上传任务不存在")
    linked=db.scalar(select(WardrobeItem).where(WardrobeItem.image_asset_id==asset.id))
    if linked:return linked
    if asset.status!="pending":raise HTTPException(409,"上传任务状态不允许创建衣物")
    duplicate=db.scalar(select(WardrobeItem).where(WardrobeItem.user_id==uid(),WardrobeItem.subcategory==body.subcategory.strip()))
    if duplicate:
        asset.status="pending_delete";asset.deleted_at=datetime.utcnow();db.commit()
        try:
            from .tasks import delete_asset
            delete_asset.delay(asset.id)
        except Exception:pass
        raise HTTPException(409,{"code":"DUPLICATE_WARDROBE_ITEM_NAME","message":f"衣橱中已经有名为“{body.subcategory.strip()}”的单品","existing_item_id":duplicate.id})
    exists=probe_object(asset.object_key)
    if exists is False:raise HTTPException(422,"图片尚未成功上传")
    if exists is None:raise HTTPException(503,"对象存储暂时不可用，请稍后重试")
    try:metadata=object_metadata(asset.object_key)
    except Exception as exc:raise HTTPException(503,"对象存储校验失败，请稍后重试") from exc
    actual_size=int(metadata.get("ContentLength",0))
    if actual_size!=asset.byte_size:raise HTTPException(422,"上传图片大小校验失败")
    asset.status="processing"
    row=WardrobeItem(id=f"item_{uuid.uuid4().hex[:8]}",user_id=uid(),wear_count=0,image_asset_id=asset.id,image_url=f"/api/v1/assets/{asset.id}",**body.model_dump(exclude={"asset_id","color"}),colors=[body.color])
    db.add(row);db.commit();db.refresh(row)
    try:
        from .tasks import process_image_asset
        process_image_asset.delay(asset.id)
    except Exception:
        pass
    return row

@router.get("/assets/{asset_id}")
def read_asset(asset_id:str,db:Session=Depends(get_db)):
    asset=db.get(ImageAsset,asset_id)
    if not asset or asset.user_id!=uid() or asset.deleted_at:raise HTTPException(404,"图片不存在")
    if asset.status=="missing":raise HTTPException(409,"图片对象缺失，已等待存储对账修复")
    key=(asset.variants or {}).get("display") or asset.object_key
    if asset.storage_backend=="local":
        path=local_path(key)
        if not path.is_file() and key!=asset.object_key and local_path(asset.object_key).is_file():
            key=asset.object_key;path=local_path(key);asset.status="processing";db.commit()
            try:
                from .tasks import process_image_asset
                process_image_asset.delay(asset.id)
            except Exception:pass
        if not path.is_file():asset.status="missing";db.commit();raise HTTPException(409,"图片原始对象缺失，请重新上传")
        return FileResponse(path,media_type="image/webp" if key.endswith(".webp") else asset.content_type,headers={"Cache-Control":"private, max-age=300"})
    exists=probe_object(key)
    if exists is False:
        original_exists=probe_object(asset.object_key) if key!=asset.object_key else False
        if original_exists is True:
            key=asset.object_key;asset.status="processing";db.commit()
            try:
                from .tasks import process_image_asset
                process_image_asset.delay(asset.id)
            except Exception:pass
        elif original_exists is None:
            raise HTTPException(503,"对象存储暂时不可用，请稍后重试")
        else:
            asset.status="missing";db.commit();raise HTTPException(409,"图片原始对象缺失，请重新上传")
    if exists is None:raise HTTPException(503,"对象存储暂时不可用，请稍后重试")
    return RedirectResponse(create_read_url(key),status_code=307)
@router.post("/outfits/generate",response_model=OutfitResponse)
def generate(body:OutfitRequest,db:Session=Depends(get_db)):
    try:
        state=run_outfit_agent(db,uid(),body)
    except OutfitWorkflowError as exc:
        raise HTTPException(422,exc.detail) from exc
    body=state["request"];items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==uid())));session=db.get(StylingSession,body.session_id) if body.session_id else None
    if session and session.user_id!=uid():session=None
    handoff=state["handoff"];results=state["results"];source=state["source"];guard=state["guard"]
    items_by_id={x.id:x for x in items}
    location=" ".join(x for x in (body.weather.city,body.weather.district) if x) or "当前地区"
    if body.weather.temperature_min_c is not None and body.weather.temperature_max_c is not None:
        temperature_fact=f"{location}当日 {body.weather.temperature_min_c:.0f}–{body.weather.temperature_max_c:.0f}℃、当前 {body.weather.temperature_c:.0f}℃、体感 {body.weather.feels_like_c:.0f}℃"
    else:
        temperature_fact=f"{location}当前 {body.weather.temperature_c:.0f}℃、体感 {body.weather.feels_like_c:.0f}℃"
    context_facts=[f"{temperature_fact}、降雨概率 {body.weather.rain_probability:.0%}"]
    if body.walking_minutes>=45:context_facts.append(f"预计步行约 {body.walking_minutes} 分钟")
    if body.formality_level>=4:context_facts.append("当天包含较正式场合")
    if body.occasion and body.occasion!="日常":context_facts.append(f"日程/要求为：{body.occasion[:100]}")
    for result_index,result in enumerate(results):
        original=result.reason
        result.reason=f"依据{'；'.join(context_facts)}。{original}"
        tips=[]
        if body.weather.rain_probability>=.5:tips.append("降雨概率较高，优先使用耐雨鞋履并携带雨具")
        if body.weather.feels_like_c>=30:tips.append("高体感温度下减少厚重叠穿，外层仅在空调环境按需使用")
        if body.walking_minutes>=45:tips.append("步行时间较长，鞋履舒适度优先于增高效果")
        if body.formality_level>=4:tips.append("正式环节保留利落外层，结束后可脱下以适应其他场景")
        selected=[items_by_id[item_id] for item_id in result.item_ids if item_id in items_by_id]
        shoes=[item for item in selected if item.category=="鞋履"]
        if body.weather.rain_probability>=.5 and shoes and not all(any(token in constraint for token in ("耐雨","防水","适合雨天") for constraint in (shoe.weather_constraints or [])) for shoe in shoes):
            result.warnings=[*result.warnings,"高降雨概率下，所选鞋履未标注耐雨或防水属性"]
        result.wearing_tips=[*tips,*result.wearing_tips][:4]
    evidence=build_evidence_pack(results,items_by_id,body);request_id=f"req_{uuid.uuid4().hex[:12]}";tasks=[task["task_id"] for task in state["image_tasks"]]
    decision_id=f"decision_{uuid.uuid4().hex[:12]}";decision=RecommendationDecision(id=decision_id,user_id=uid(),context_key=context_key(body.occasion),request_snapshot=body.model_dump(mode="json"),feature_schema_version="features-v3",ranking_model_version=state.get("ranking_model_version","rules-v1"),policy_version=state.get("policy_version","pairwise-control-v1"));db.add(decision);db.flush()
    result_sets={frozenset(result.item_ids):index+1 for index,result in enumerate(results)};impressions={};serialized=state.get("candidates",[]);denominator=sum(pow(2.7182818,float(row["total"])*4) for row in serialized) or 1
    for row in serialized:
        ids=row["item_ids"];position=result_sets.get(frozenset(ids));impression_id=f"imp_{uuid.uuid4().hex[:12]}";features=candidate_features([items_by_id[x] for x in ids if x in items_by_id],row["scores"]);probability=float(row["scores"].get("pairwise_probability",row["scores"].get("learned_probability",.5)));uncertainty=float(row["scores"].get("bandit_uncertainty",0));propensity=float(row["scores"].get("selection_probability",pow(2.7182818,float(row["total"])*4)/denominator))
        db.add(CandidateImpression(id=impression_id,decision_id=decision_id,user_id=uid(),item_ids=ids,feature_snapshot=features,base_score=float(row["scores"].get("base_total",row["total"])),predicted_probability=probability,uncertainty=uncertainty,final_score=float(row["total"]),position=position,displayed=position is not None,selection_probability=propensity));impressions[frozenset(ids)]=impression_id
    for result_index,result in enumerate(results):
        oid=f"outfit_{uuid.uuid4().hex[:10]}";result.outfit_id=oid
        stored_result={**result.model_dump(),"request_id":request_id,"generated_by":source,"decision_id":decision_id,"impression_id":impressions.get(frozenset(result.item_ids)),"ranking_model_version":decision.ranking_model_version,"policy_version":decision.policy_version}
        db.add(Outfit(id=oid,user_id=uid(),mode=body.mode,occasion=body.occasion,item_ids=result.item_ids,result=stored_result))
        evidence_row=evidence[result_index]
        for dimension in evidence_row["dimensions"]:db.add(RecommendationEvidence(outfit_id=oid,dimension=dimension["dimension"],score=dimension["score"],reasons=[dimension["claim"],*dimension["facts"]],source_refs=dimension["source_refs"]))
    for task in state["image_tasks"]:db.add(ImageTask(id=task["task_id"],user_id=uid(),kind=task["kind"],status="queued"))
    if body.session_id:
        session=session or StylingSession(session_id=body.session_id,user_id=uid(),turns=[],last_handoff={},last_outfits=[])
        session.turns=([*session.turns,{"role":"user","text":body.occasion},{"role":"assistant","outfit_item_ids":[x.item_ids for x in results]}])[-12:];session.last_handoff=handoff;session.last_outfits=[x.model_dump() for x in results];db.add(session)
    db.commit()
    if body.session_id:cache_styling_session(uid(),body.session_id,{"turns":session.turns,"last_handoff":session.last_handoff,"last_outfits":session.last_outfits})
    return OutfitResponse(request_id=request_id,outfits=results,generated_by=source,preview_task_ids=tasks,intent_understanding=handoff,evidence_pack=evidence,answer_guard=guard)
@router.get("/outfits/recent")
def recent_outfits(limit:int=12,db:Session=Depends(get_db)):
    requested=max(1,min(50,limit));scan_limit=max(requested,50 if requested>=3 else requested)
    rows=list(db.scalars(select(Outfit).where(Outfit.user_id==uid()).order_by(Outfit.created_at.desc()).limit(scan_limit)))
    if requested==3:
        by_role={}
        for row in rows:
            role=(row.result or {}).get("kind")
            if role in {"主推荐","舒适备选","风格备选"} and role not in by_role:by_role[role]=row
        selected=[by_role[role] for role in ("主推荐","舒适备选","风格备选") if role in by_role]
        if len(selected)==3:rows=selected
        else:rows=rows[:requested]
    else:rows=rows[:requested]
    return [{"outfit_id":row.id,"occasion":row.occasion,"item_ids":row.item_ids,**(row.result or {})} for row in rows]
@router.get("/outfits/{outfit_id}/evidence")
def outfit_evidence(outfit_id:str,db:Session=Depends(get_db)):
    outfit=db.get(Outfit,outfit_id)
    if not outfit or outfit.user_id!=uid():raise HTTPException(404,"outfit not found")
    rows=list(db.scalars(select(RecommendationEvidence).where(RecommendationEvidence.outfit_id==outfit_id).order_by(RecommendationEvidence.id)))
    result=outfit.result or {};impression=db.get(CandidateImpression,result.get("impression_id")) if result.get("impression_id") else None;model=db.scalar(select(RankingModel).where(RankingModel.version==result.get("ranking_model_version"))) if result.get("ranking_model_version") else None
    weights=(model.parameters or {}).get("weights",{}) if model else {};attribution=sorted([{"feature":key,"value":value,"weight":weights.get(key,0),"contribution":round(value*weights.get(key,0),4)} for key,value in (impression.feature_snapshot if impression else {}).items() if key!="bias"],key=lambda row:abs(row["contribution"]),reverse=True)
    return {"outfit_id":outfit_id,"item_ids":outfit.item_ids,"decision_id":result.get("decision_id"),"ranking_model_version":result.get("ranking_model_version"),"policy_version":result.get("policy_version"),"dimensions":[{"dimension":row.dimension,"score":row.score,"claim":row.reasons[0] if row.reasons else "","facts":row.reasons[1:] if row.reasons else [],"source_refs":row.source_refs} for row in rows],"model_attribution":attribution,"limitations":["分数用于候选间相对排序，不应解释为穿搭成功概率"]}
@router.patch("/outfits/{outfit_id}/tryon-result")
def save_tryon_result(outfit_id:str,result_url:str,db:Session=Depends(get_db)):
    row=db.get(Outfit,outfit_id)
    if not row or row.user_id!=uid():raise HTTPException(404,"outfit not found")
    row.result={**(row.result or {}),"tryon_result_url":result_url};db.commit();return {"saved":True,"outfit_id":outfit_id,"tryon_result_url":result_url}
@router.post("/outfits/replace-item",status_code=201)
def replace_outfit_item(body:ReplaceOutfitItemIn,db:Session=Depends(get_db)):
    source=db.get(Outfit,body.outfit_id);target=db.get(WardrobeItem,body.item_id)
    if not source or source.user_id!=uid():raise HTTPException(404,"outfit not found")
    if not target or target.user_id!=uid() or target.id not in source.item_ids:raise HTTPException(404,"outfit item not found")
    new_ids=[item_id for item_id in source.item_ids if item_id!=target.id]
    replacement=None
    if body.mode!="remove":
        all_candidates=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==uid(),WardrobeItem.id.notin_(source.item_ids))))
        if body.replacement_item_id:
            replacement=next((item for item in all_candidates if item.id==body.replacement_item_id),None)
            if not replacement:raise HTTPException(422,{"code":"REPLACEMENT_ITEM_UNAVAILABLE","message":"所选替代单品不存在或已经在这套穿搭中"})
            candidates=[]
        else:
            candidates=[item for item in all_candidates if item.category==target.category]
            if target.category in {"上装","外套"}:candidates=[item for item in candidates if item.wearing_layer==target.wearing_layer]
        slot_candidates=list(candidates)
        if body.mode=="different_color":candidates=[item for item in candidates if set(item.colors).isdisjoint(target.colors)]
        if body.mode=="different_style":candidates=[item for item in candidates if set(item.styles).isdisjoint(target.styles)]
        def replacement_score(item):
            color=len(set(item.colors)&set(target.colors));style=len(set(item.styles)&set(target.styles));fit=1 if item.fit==target.fit else 0
            return (color*3+style*2+fit,-item.wear_count) if body.mode=="similar" else (style+fit if body.mode=="different_color" else color+fit,-item.wear_count)
        if not replacement:
            replacement=max(candidates,key=replacement_score) if candidates else max(slot_candidates,key=replacement_score) if slot_candidates else None
        if not replacement:raise HTTPException(422,{"code":"NO_SMART_REPLACEMENT_AVAILABLE","message":"衣橱中没有同槽位的智能替代候选；你仍可使用“自由选择”明确指定任意单品"})
        position=source.item_ids.index(target.id);new_ids.insert(position,replacement.id)
    items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.id.in_(new_ids)))) if new_ids else []
    by_id={item.id:item for item in items};ordered=[by_id[item_id] for item_id in new_ids if item_id in by_id]
    mode_text={"similar":"相似单品","different_color":"不同颜色","different_style":"不同风格","remove":"移除单品","custom":"自由选择"}[body.mode]
    counts={category:sum(item.category==category for item in ordered) for category in {"下装","鞋履"}}
    structure_warnings=[f"当前包含 {count} 件{category}，生成换装前请确认这是你的明确意图" for category,count in counts.items() if count>1]
    oid=f"outfit_{uuid.uuid4().hex[:10]}";result={**(source.result or {}),"outfit_id":oid,"item_ids":new_ids,"title":" × ".join(item.subcategory for item in ordered),"reason":f"保留其余单品，仅对{target.subcategory}执行了{mode_text}。","warnings":structure_warnings,"tryon_result_url":None,"replaced_from_outfit_id":source.id}
    row=Outfit(id=oid,user_id=uid(),mode=source.mode,occasion=source.occasion,item_ids=new_ids,result=result);db.add(row);db.commit()
    return result
@router.post("/feedback",status_code=201)
def feedback(body:FeedbackIn,db:Session=Depends(get_db)):
    outfit=db.get(Outfit,body.outfit_id)
    if not outfit or outfit.user_id!=uid(): raise HTTPException(404,"outfit not found")
    replaced_today=False
    if body.adopted:
        day_start=datetime.combine(datetime.now().date(),datetime.min.time());day_end=day_start+timedelta(days=1)
        today_rows=list(db.scalars(select(WearHistory).where(WearHistory.user_id==uid(),WearHistory.worn_at>=day_start,WearHistory.worn_at<day_end)))
        if any(row.outfit_id==body.outfit_id for row in today_rows):return {"recorded":False,"duplicate":True,"replaced_today":False}
        previous=[row for row in today_rows if row.outfit_id!=body.outfit_id]
        if previous and not body.replace_today:
            raise HTTPException(409,{"code":"today_outfit_exists","message":"今天已经记录了一套穿搭，确认后可以替换。","outfit_ids":[row.outfit_id for row in previous]})
        if previous:
            previous_outfits={row.outfit_id:db.get(Outfit,row.outfit_id) for row in previous}
            old_item_ids={item_id for old in previous_outfits.values() if old for item_id in old.item_ids}
            for row in previous:db.delete(row)
            old_feedback=list(db.scalars(select(OutfitFeedback).where(OutfitFeedback.outfit_id.in_(list(previous_outfits)),OutfitFeedback.adopted==True)))
            for row in old_feedback:
                old_outfit=previous_outfits.get(row.outfit_id);old_impression_id=(old_outfit.result or {}).get("impression_id") if old_outfit else None;old_outcome=db.scalar(select(DecisionOutcome).where(DecisionOutcome.impression_id==old_impression_id)) if old_impression_id else None
                if old_outcome:
                    correction=-.8-old_outcome.reward;old_outcome.reward=-.8;old_outcome.adopted=False;old_outcome.replaced_item_ids=list(old_outfit.item_ids)
                    old_impression=db.get(CandidateImpression,old_impression_id)
                    if old_impression:update_thompson(db,uid(),context_key(old_outfit.occasion),old_impression.feature_snapshot,correction)
                db.delete(row)
            db.flush()
            remaining_history=list(db.scalars(select(WearHistory).where(WearHistory.user_id==uid())))
            remaining_outfits={row.outfit_id:db.get(Outfit,row.outfit_id) for row in remaining_history}
            for item in db.scalars(select(WardrobeItem).where(WardrobeItem.id.in_(old_item_ids))):
                item.wear_count=max(0,item.wear_count-1)
                item.last_worn_at=max((row.worn_at for row in remaining_history if remaining_outfits.get(row.outfit_id) and item.id in remaining_outfits[row.outfit_id].item_ids),default=None)
            replaced_today=True
    existing=db.scalar(select(OutfitFeedback).where(OutfitFeedback.outfit_id==body.outfit_id,OutfitFeedback.adopted==body.adopted))
    if existing:return {"recorded":False,"duplicate":True}
    feedback_data=body.model_dump(exclude={"replace_today"});row=OutfitFeedback(**feedback_data);db.add(row);db.flush();learn_from_feedback(db,uid(),row,outfit)
    result=outfit.result or {};impression_id=result.get("impression_id");decision_id=result.get("decision_id")
    if impression_id and decision_id and not db.scalar(select(DecisionOutcome).where(DecisionOutcome.impression_id==impression_id)):
        impression=db.get(CandidateImpression,impression_id);reward=outcome_reward(body.adopted,body.replaced_item_ids,body.feedback_tags);delay=max(0,int((datetime.utcnow()-outfit.created_at).total_seconds()))
        db.add(DecisionOutcome(decision_id=decision_id,impression_id=impression_id,outfit_id=outfit.id,reward=reward,adopted=body.adopted,replaced_item_ids=body.replaced_item_ids,feedback_delay_seconds=delay))
        if impression:update_thompson(db,uid(),context_key(outfit.occasion),impression.feature_snapshot,reward)
        detect_preference_drift(db,uid(),context_key(outfit.occasion))
    if body.adopted:
        db.add(WearHistory(user_id=uid(),outfit_id=body.outfit_id))
        for item in db.scalars(select(WardrobeItem).where(WardrobeItem.id.in_(outfit.item_ids))):
            item.wear_count+=1;item.last_worn_at=datetime.utcnow()
    db.commit();invalidate_preferences(uid(),context_key(outfit.occasion));return {"recorded":True,"replaced_today":replaced_today}
@router.get("/calendar")
def calendar(db:Session=Depends(get_db)):
    rows=list(db.scalars(select(WearHistory).where(WearHistory.user_id==uid()).order_by(WearHistory.worn_at.desc())))
    result=[]
    for row in rows:
        outfit=db.get(Outfit,row.outfit_id)
        item_ids=outfit.item_ids if outfit else []
        items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.id.in_(item_ids)))) if item_ids else []
        result.append({"id":row.id,"outfit_id":row.outfit_id,"worn_at":row.worn_at,"occasion":outfit.occasion if outfit else None,"item_ids":item_ids,"items":[WardrobeItemOut.model_validate(x).model_dump() for x in items]})
    return result
def _delete_temporary_photo(asset:PhotoAsset,db:Session):
    generated=(Path(__file__).resolve().parents[1]/"generated").resolve();target=Path(asset.storage_key).resolve()
    if target.is_relative_to(generated):target.unlink(missing_ok=True)
    asset.deleted_at=datetime.utcnow();db.commit()
@router.post("/photos/upload",status_code=201)
async def upload_photo(file:UploadFile=File(...),db:Session=Depends(get_db)):
    if not (file.content_type or "").startswith("image/"):raise HTTPException(415,"仅支持图片文件")
    content=await file.read()
    if not content or len(content)>12*1024*1024:raise HTTPException(422,"图片为空或超过 12MB")
    suffix=Path(file.filename or "outfit.jpg").suffix.lower();suffix=suffix if suffix in {".jpg",".jpeg",".png",".webp"} else ".jpg"
    generated=Path(__file__).resolve().parents[1]/"generated";generated.mkdir(parents=True,exist_ok=True)
    asset_id=f"photo_{uuid.uuid4().hex[:12]}";filename=f"{asset_id}{suffix}";(generated/filename).write_bytes(content)
    row=PhotoAsset(id=asset_id,user_id=uid(),kind="outfit_check",storage_key=str(generated/filename),retention="temporary");db.add(row);db.commit()
    return {"asset_id":asset_id,"image_url":f"/generated/{filename}"}
@router.post("/photos/analyze-v2",response_model=AdvancedPhotoAnalysis)
async def analyze_photo_v2(asset_id:str,save_to_calendar:bool=False,occasion:str="日常通勤",weather:str="未提供",db:Session=Depends(get_db)):
    asset=db.get(PhotoAsset,asset_id)
    if not asset or asset.user_id!=uid() or asset.deleted_at:raise HTTPException(404,"photo asset not found")
    path=Path(asset.storage_key)
    if not path.exists():raise HTTPException(410,"temporary photo file no longer exists")
    wardrobe=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==uid())))
    try:
        result=await analyze_outfit_image(path,wardrobe,occasion,weather)
        return result.model_copy(update={"deleted_after_analysis":not save_to_calendar})
    except Exception as exc:
        message=str(exc)
        if "API Key" in message:raise HTTPException(503,{"code":"VISION_MODEL_NOT_CONFIGURED","message":message})
        raise HTTPException(502,{"code":"VISION_ANALYSIS_FAILED","message":message[:300]})
    finally:
        if not save_to_calendar:_delete_temporary_photo(asset,db)
@router.get("/tasks/{task_id}")
def task(task_id:str,db:Session=Depends(get_db)):
    row=db.get(ImageTask,task_id)
    if not row or row.user_id!=uid(): raise HTTPException(404,"task not found")
    return {"id":row.id,"status":row.status,"result_url":row.result_url}
@router.get("/tasks/{task_id}/events")
async def task_events(task_id:str,db:Session=Depends(get_db)):
    row=db.get(ImageTask,task_id)
    if not row or row.user_id!=uid():raise HTTPException(404,"task not found")
    async def events():
        for state in ["queued","processing","completed"]:
            yield f"event: progress\ndata: {json.dumps({'task_id':task_id,'status':state})}\n\n"; await asyncio.sleep(.15)
    return StreamingResponse(events(),media_type="text/event-stream")
@router.post("/privacy/deletion-requests",status_code=202)
def delete_data(scope:str="photos_and_profile",db:Session=Depends(get_db)):
    row=DeletionRequest(id=f"del_{uuid.uuid4().hex[:12]}",user_id=uid(),scope=scope,status="queued");db.add(row);db.commit();return {"request_id":row.id,"status":row.status}

@router.post("/weekly-plans",response_model=WeeklyPlanResult,status_code=201)
def weekly_plan(body:WeeklyPlanRequest,db:Session=Depends(get_db)):return create_weekly_plan(db,uid(),body)
@router.patch("/weekly-plans/{plan_id}",response_model=WeeklyPlanResult)
def weekly_replan(plan_id:str,body:ReplanRequest,db:Session=Depends(get_db)):
    try:return replan_dates(db,uid(),plan_id,body)
    except ValueError as exc:raise HTTPException(404,str(exc))
@router.get("/weekly-plans/{plan_id}")
def get_weekly_plan(plan_id:str,db:Session=Depends(get_db)):
    plan=db.get(WeeklyPlan,plan_id)
    if not plan or plan.user_id!=uid():raise HTTPException(404,"plan not found")
    return {"id":plan.id,"version":plan.version,"start_date":plan.start_date,"days":list(db.scalars(select(PlanDay).where(PlanDay.plan_id==plan_id).order_by(PlanDay.date))),"summary":plan.summary}
@router.post("/wardrobe/graph/rebuild",response_model=WardrobeGraphResult)
def graph_rebuild(db:Session=Depends(get_db)):return rebuild_graph(db,uid())
@router.post("/travel-plans",response_model=TravelPlanResult,status_code=201)
def travel_plan(body:TravelPlanRequest,db:Session=Depends(get_db)):return create_travel_plan(db,uid(),body)
@router.post("/multi-scene-plans",response_model=MultiSceneResult,status_code=201)
def multi_scene(body:MultiSceneRequest,db:Session=Depends(get_db)):return create_multiscene_plan(db,uid(),body)
@router.post("/style-identity/rebuild",response_model=StyleIdentityResult)
def style_identity(db:Session=Depends(get_db)):return build_style_identity(db,uid())
@router.get("/long-term-plan")
def wardrobe_long_term(db:Session=Depends(get_db)):return long_term_plan(db,uid())
@router.post("/purchase/analyze",response_model=PurchaseResult,status_code=201)
def purchase(body:PurchaseCandidate,db:Session=Depends(get_db)):return analyze_purchase(db,uid(),body)
@router.post("/behavior/signals",status_code=201)
def behavior_signal(body:BehaviorSignalIn,db:Session=Depends(get_db)):
    row=db.scalar(select(BehaviorFeature).where(BehaviorFeature.user_id==uid(),BehaviorFeature.context_key==body.context_key,BehaviorFeature.feature_key==body.feature_key))
    if not row:row=BehaviorFeature(user_id=uid(),context_key=body.context_key,feature_key=body.feature_key,value=body.value,evidence_count=1,source=body.source)
    else:row.value=(row.value*row.evidence_count+body.value)/(row.evidence_count+1);row.evidence_count+=1;row.source=body.source
    db.add(row);db.commit();return {"recorded":True,"feature_key":row.feature_key,"value":row.value,"item_id":body.item_id}
@router.get("/personalization/metrics")
def personalization_metrics(db:Session=Depends(get_db)):
    outfits=list(db.scalars(select(Outfit).where(Outfit.user_id==uid()).order_by(Outfit.created_at)))
    feedback_rows=list(db.scalars(select(OutfitFeedback).join(Outfit,Outfit.id==OutfitFeedback.outfit_id).where(Outfit.user_id==uid()).order_by(OutfitFeedback.created_at)))
    feedback_by_outfit={row.outfit_id:row for row in feedback_rows};original=[row for row in outfits if not (row.result or {}).get("replaced_from_outfit_id")]
    request_ids={(row.result or {}).get("request_id") for row in original if (row.result or {}).get("request_id")};generated_batches=len(request_ids) or (len(original)+2)//3
    adopted=sum(bool(row.adopted) for row in feedback_rows);rejected=sum(not row.adopted for row in feedback_rows);replacements=sum(bool((row.result or {}).get("replaced_from_outfit_id")) for row in outfits)
    decided_outfits={row.outfit_id for row in feedback_rows};decisions=len(decided_outfits)
    fallback_batches=len({(row.result or {}).get("request_id") for row in original if (row.result or {}).get("generated_by") in {"rules","rules_fast","guarded_rules"} and (row.result or {}).get("request_id")})
    rates=[1 if row.replaced_item_ids else 0 for row in feedback_rows];split=max(1,len(rates)//2);early=sum(rates[:split])/max(1,len(rates[:split]));recent=sum(rates[split:])/max(1,len(rates[split:]));profiles=list(db.scalars(select(ContextProfile).where(ContextProfile.user_id==uid())))
    contexts={}
    for outfit in outfits:
        key=context_key(outfit.occasion);entry=contexts.setdefault(key,{"generated":0,"adopted":0,"rejected":0,"replacements":0})
        entry["generated"]+=1
        if (outfit.result or {}).get("replaced_from_outfit_id"):entry["replacements"]+=1
        feedback=feedback_by_outfit.get(outfit.id)
        if feedback:entry["adopted" if feedback.adopted else "rejected"]+=1
    learning={key:{k:v for k,v in feedback_affinities(db,uid(),key).items() if k!="values"} for key in ("work","date","travel","important","weekend")}
    return {"samples":len(feedback_rows),"funnel":{"recommendation_batches":generated_batches,"outfits_generated":len(original),"outfits_decided":decisions,"adopted":adopted,"rejected":rejected,"replacement_actions":replacements,"adoption_rate":round(adopted/max(1,decisions),3),"rejection_rate":round(rejected/max(1,decisions),3),"replacement_rate":round(replacements/max(1,generated_batches),3),"rule_fallback_rate":round(fallback_batches/max(1,generated_batches),3)},"early_replacement_rate":round(early,3),"recent_replacement_rate":round(recent,3),"improvement":round(early-recent,3),"by_context":contexts,"context_profiles":[{"key":x.context_key,"weights":x.weights,"sample_count":x.sample_count} for x in profiles],"learning":learning}
@router.post("/personalization/train",status_code=201)
def train_personalized_ranker(db:Session=Depends(get_db)):return train_and_evaluate(db)
@router.get("/personalization/models")
def personalization_models(db:Session=Depends(get_db)):
    return [{"version":row.version,"model_type":row.model_type,"status":row.status,"metrics":row.metrics,"training_window":row.training_window,"created_at":row.created_at} for row in db.scalars(select(RankingModel).order_by(RankingModel.created_at.desc()).limit(20))]
@router.get("/personalization/drift")
def preference_drift(db:Session=Depends(get_db)):
    return [{"id":row.id,"context_key":row.context_key,"feature_key":row.feature_key,"long_term_value":row.long_term_value,"recent_value":row.recent_value,"magnitude":row.magnitude,"status":row.status,"created_at":row.created_at} for row in db.scalars(select(PreferenceDriftEvent).where(PreferenceDriftEvent.user_id==uid()).order_by(PreferenceDriftEvent.created_at.desc()).limit(50))]
@router.get("/personalization/experiment")
def personalization_experiment(db:Session=Depends(get_db)):
    row=db.scalar(select(PolicyAssignment).where(PolicyAssignment.user_id==uid()).order_by(PolicyAssignment.assigned_at.desc()))
    return {"experiment_key":row.experiment_key,"variant":row.variant,"assigned_at":row.assigned_at} if row else {"experiment_key":"ranking-policy-v4","variant":"not_assigned"}
@router.post("/outfits/{outfit_id}/counterfactual")
def outfit_counterfactual(outfit_id:str,changes:dict,db:Session=Depends(get_db)):
    outfit=db.get(Outfit,outfit_id)
    if not outfit or outfit.user_id!=uid():raise HTTPException(404,"outfit not found")
    impression_id=(outfit.result or {}).get("impression_id");impression=db.get(CandidateImpression,impression_id) if impression_id else None
    if not impression:raise HTTPException(404,"decision snapshot not found")
    allowed={"weather","occasion","preference","color","proportion","utilization","freshness","personalization","repeat_penalty"};safe_changes={key:max(0,min(1,float(value))) for key,value in changes.items() if key in allowed}
    if not safe_changes:raise HTTPException(422,"没有可重算的受支持特征")
    version=(outfit.result or {}).get("ranking_model_version");model=db.scalar(select(RankingModel).where(RankingModel.version==version)) if version else None
    return {"outfit_id":outfit_id,"model_version":version,**counterfactual(impression.feature_snapshot,model,safe_changes)}
@router.get("/integrations")
def integrations(db:Session=Depends(get_db)):
    rows=list(db.scalars(select(AuthorizedIntegration).where(AuthorizedIntegration.user_id==uid()).order_by(AuthorizedIntegration.provider)))
    result=[{"id":row.id,"provider":row.provider,"scopes":row.scopes,"status":row.status,"last_synced_at":row.last_synced_at} for row in rows]
    result.append({"id":"open-meteo","provider":"weather","scopes":["weather:read"],"status":"connected","last_synced_at":None})
    return result
@router.get("/weather/current")
async def current_weather(city:str=Query("深圳市",min_length=1,max_length=80),district:str|None=None,latitude:float|None=None,longitude:float|None=None,date:str|None=None):
    try:return await open_meteo_weather(city,latitude,longitude,district,date)
    except (ValueError,httpx.HTTPError) as exc:raise HTTPException(502,{"code":"WEATHER_UNAVAILABLE","message":str(exc)})
@router.get("/integrations/outlook/authorize")
def outlook_authorize():
    try:return {"authorization_url":outlook_authorization_url(uid())}
    except RuntimeError as exc:raise HTTPException(503,{"code":"OUTLOOK_NOT_CONFIGURED","message":str(exc)})
@router.get("/integrations/outlook/callback")
async def outlook_callback(code:str|None=None,state:str|None=None,error:str|None=None,db:Session=Depends(get_db)):
    if error or not code or not state:return RedirectResponse(f"{settings.frontend_url}/settings/privacy?outlook=error")
    try:
        user_id=read_oauth_state(state);token=await exchange_outlook_code(code);token["saved_at"]=int(datetime.utcnow().timestamp())
        row=db.scalar(select(AuthorizedIntegration).where(AuthorizedIntegration.user_id==user_id,AuthorizedIntegration.provider=="outlook"))
        if not row:row=AuthorizedIntegration(id=f"int_{uuid.uuid4().hex[:10]}",user_id=user_id,provider="outlook",scopes=["Calendars.Read"],status="connected")
        row.status="connected";row.scopes=["Calendars.Read"];row.encrypted_credential_ref=encrypt_credentials(token);row.last_synced_at=datetime.utcnow();db.add(row);record_access(db,user_id,"user","grant","outlook",row.id,"用户通过 Microsoft OAuth 授予日历只读权限",{"scopes":row.scopes});db.commit()
        return RedirectResponse(f"{settings.frontend_url}/settings/privacy?outlook=connected")
    except Exception:return RedirectResponse(f"{settings.frontend_url}/settings/privacy?outlook=error")
@router.get("/integrations/outlook/events")
async def get_outlook_events(days:int=Query(14,ge=1,le=30),db:Session=Depends(get_db)):
    try:
        events=await outlook_events(db,uid(),days);record_access(db,uid(),"proactive_agent","read","outlook",None,"读取未来日程用于穿搭计划",{"days":days});db.commit();return events
    except PermissionError as exc:raise HTTPException(403,{"code":"OUTLOOK_SCOPE_REQUIRED","message":str(exc)})
    except httpx.HTTPError as exc:raise HTTPException(502,{"code":"OUTLOOK_UNAVAILABLE","message":str(exc)})
@router.post("/integrations/{provider}",status_code=201)
def integration(provider:str,scopes:list[str]=Query(...),db:Session=Depends(get_db)):
    row=connect_integration(db,uid(),provider,scopes);return {"id":row.id,"provider":row.provider,"scopes":row.scopes,"status":row.status}
@router.delete("/integrations/{provider}")
def disconnect_integration(provider:str,db:Session=Depends(get_db)):
    row=db.scalar(select(AuthorizedIntegration).where(AuthorizedIntegration.user_id==uid(),AuthorizedIntegration.provider==provider))
    if not row:raise HTTPException(404,"integration not found")
    row.status="disconnected";row.encrypted_credential_ref=None;record_access(db,uid(),"user","revoke",provider,row.id,"用户撤销授权");db.commit();return {"disconnected":True}
@router.post("/proactive/events",status_code=201)
def proactive_event(body:ProactiveEventIn,db:Session=Depends(get_db)):
    try:return ingest_event(db,uid(),body)
    except PermissionError as exc:raise HTTPException(403,{"code":"SCOPE_REQUIRED","message":str(exc)})
@router.get("/proactive/alerts")
def proactive_alerts(db:Session=Depends(get_db)):return scan_due_events(db,uid())
@router.get("/notification-preferences")
def notification_preferences(db:Session=Depends(get_db)):return db.get(NotificationPreference,uid()) or NotificationPreference(user_id=uid())
@router.put("/notification-preferences")
def update_notification_preferences(body:NotificationPreferencesIn,db:Session=Depends(get_db)):
    row=db.get(NotificationPreference,uid()) or NotificationPreference(user_id=uid())
    for k,v in body.model_dump().items():setattr(row,k,v)
    db.add(row);db.commit();return row
@router.get("/privacy/access-log")
def access_log(db:Session=Depends(get_db)):return list(db.scalars(select(AccessLog).where(AccessLog.user_id==uid()).order_by(AccessLog.created_at.desc()).limit(100)))
@router.post("/try-on/v3",status_code=202)
def tryon_v3(body:TryOnRequest,db:Session=Depends(get_db)):
    if not body.preserve_identity:raise HTTPException(422,"V3 try-on requires identity preservation")
    payload=tryon_task_payload(body.person_asset_id,body.outfit_id,body.views,body.outerwear_state);db.add(ImageTask(id=payload["task_id"],user_id=uid(),kind="identity_preserving_tryon",status="queued"));db.commit();return payload
@router.post("/try-on/generate")
async def tryon_generate(person:UploadFile=File(...),garment:UploadFile=File(...),prompt:str|None=Form(None)):
    return await generate_tryon(person,garment,prompt)
