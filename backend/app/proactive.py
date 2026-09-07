import hashlib,uuid
from datetime import timedelta
from .time_utils import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import AuthorizedIntegration,ProactiveEvent,NotificationPreference,AccessLog
from .schemas import ProactiveEventIn
from .config import settings

def record_access(db:Session,user_id:str,actor:str,action:str,resource_type:str,resource_id:str|None,purpose:str,metadata:dict|None=None):
    db.add(AccessLog(user_id=user_id,actor=actor,action=action,resource_type=resource_type,resource_id=resource_id,purpose=purpose,metadata_json=metadata or {}))

def ensure_scope(db:Session,user_id:str,provider:str,scope:str):
    integration=db.scalar(select(AuthorizedIntegration).where(AuthorizedIntegration.user_id==user_id,AuthorizedIntegration.provider==provider,AuthorizedIntegration.status=="connected"))
    if not integration or scope not in integration.scopes:raise PermissionError(f"missing authorized scope: {provider}:{scope}")
    record_access(db,user_id,"proactive_agent","read",provider,integration.id,"生成用户主动授权的穿搭计划",{"scope":scope})

def connect_integration(db:Session,user_id:str,provider:str,scopes:list[str]):
    row=db.scalar(select(AuthorizedIntegration).where(AuthorizedIntegration.user_id==user_id,AuthorizedIntegration.provider==provider))
    if not row:row=AuthorizedIntegration(id=f"int_{uuid.uuid4().hex[:10]}",user_id=user_id,provider=provider,scopes=scopes,status="connected")
    else:row.scopes=scopes;row.status="connected";row.last_synced_at=datetime.utcnow()
    db.add(row);record_access(db,user_id,"user","grant",provider,row.id,"用户主动授权",{"scopes":scopes});db.commit();return row

def ingest_event(db:Session,user_id:str,body:ProactiveEventIn):
    provider=body.source_scope.replace(":",".").split(".")[0]
    ensure_scope(db,user_id,provider,body.source_scope)
    key=hashlib.sha256(f"{user_id}:{body.event_type}:{body.scheduled_for.isoformat()}:{body.payload.get('title','')}".encode()).hexdigest()[:24]
    exists=db.scalar(select(ProactiveEvent).where(ProactiveEvent.user_id==user_id,ProactiveEvent.dedupe_key==key,ProactiveEvent.status!="cancelled"))
    if exists:return exists
    row=ProactiveEvent(id=f"evt_{uuid.uuid4().hex[:10]}",user_id=user_id,event_type=body.event_type,importance=body.importance,scheduled_for=body.scheduled_for,payload=body.payload,status="pending",dedupe_key=key);db.add(row);db.commit();return row

def scan_due_events(db:Session,user_id:str,now:datetime|None=None):
    now=now or datetime.utcnow();prefs=db.get(NotificationPreference,user_id) or NotificationPreference(user_id=user_id)
    if not prefs.enabled:return []
    events=list(db.scalars(select(ProactiveEvent).where(ProactiveEvent.user_id==user_id,ProactiveEvent.status=="pending",ProactiveEvent.scheduled_for<=now+timedelta(hours=48)).order_by(ProactiveEvent.scheduled_for)))
    alerts=[]
    for event in events:
        if prefs.important_events_only and event.importance<.7:continue
        alerts.append({"event_id":event.id,"title":event.payload.get("title","重要行程穿搭已准备"),"scheduled_for":event.scheduled_for.isoformat(),"message":_message(event),"actions":["查看两套方案","稍后提醒","忽略本次"]});event.status="notified"
    db.add(prefs);db.commit();return alerts

def _message(event:ProactiveEvent):
    weather=event.payload.get("weather",{});temp=weather.get("temperature_c");rain=weather.get("rain_probability")
    details=[]
    if temp is not None:details.append(f"预计 {temp}℃")
    if rain and rain>.35:details.append("可能有雨")
    return f"{event.payload.get('title','重要日程')}将在近期开始，{'、'.join(details)}。已准备正式度与步行舒适度不同的两套方案。"

async def run_agents_sdk_planner(user_id:str,prompt:str):
    """主动规划 LLM 链路。使用任意 OpenAI 兼容接口（Chat Completions），不依赖 OpenAI Agents SDK。"""
    if not settings.openai_api_key:
        return {"source":"deterministic_fallback","output":prompt,"warning":"OPENAI_API_KEY not configured"}
    try:
        from openai import AsyncOpenAI
        client=AsyncOpenAI(api_key=settings.openai_api_key,base_url=settings.openai_base_url)
        response=await client.chat.completions.create(
            model=settings.openai_planning_model or settings.openai_model,
            messages=[
                {"role":"system","content":"在明确授权证据范围内，为重要日程生成克制、可执行、低打扰的穿搭准备。不得读取未授权数据；外部通知必须由应用权限层批准。用简洁中文输出。"},
                {"role":"user","content":prompt},
            ],
            temperature=0.6,
            max_tokens=2000,
        )
        content=response.choices[0].message.content or ""
        return {"source":"chat_completions","output":content}
    except Exception as exc:return {"source":"deterministic_fallback","output":prompt,"warning":str(exc)[:240]}
