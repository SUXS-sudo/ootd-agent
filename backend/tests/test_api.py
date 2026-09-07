import os
import uuid
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
os.environ.setdefault("DATABASE_URL", "mysql+pymysql://ootd:ootd@localhost:3306/ootd_test?charset=utf8mb4")
os.environ.setdefault("LANGGRAPH_CHECKPOINT_URL", "mysql://ootd:ootd@localhost:3306/ootd_checkpoints_test?charset=utf8mb4")
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import ImageAsset,WardrobeItem
from app.config import settings
from app.object_storage import local_path

def upload_wardrobe_item(client:TestClient,content:bytes,name:str,category:str="上装",color:str="白色",**attributes):
    signed=client.post("/api/v1/uploads/sign",json={"filename":"item.png","content_type":"image/png","byte_size":len(content),"kind":"wardrobe"})
    assert signed.status_code==200,signed.text
    ticket=signed.json()
    uploaded=client.put(ticket["upload_url"],content=content,headers={"Content-Type":"image/png"})
    assert uploaded.status_code==204,uploaded.text
    payload={"asset_id":ticket["asset_id"],"category":category,"subcategory":name,"color":color,**attributes}
    return client.post("/api/v1/wardrobe/from-upload",json=payload)

def test_demo_profile_uses_the_same_blank_preference_defaults():
    with TestClient(app) as client:
        profile=client.get("/api/v1/profile").json()
        assert profile["height_cm"] is None
        assert profile["temperature_preference"]==""
        for field in ("preferred_styles","avoided_styles","preferred_item_terms","avoided_item_terms","preferred_colors","avoided_colors","restrictions","visual_goals"):
            assert profile[field]==[]

def item_payload(name):
    return {"category":"上装","subcategory":name,"colors":["蓝色"],"material_guess":[],"material_confidence":0,"pattern":"纯色","fit":"常规","length":"常规","wearing_layer":"主上装","warmth_level":2,"formality_level":2,"styles":[],"seasons":["四季"],"weather_constraints":[],"clean_status":"可穿","image_url":None}

def test_users_have_isolated_wardrobes():
    with TestClient(app) as client:
        alice={"x-ootd-dev-user":"alice@example.test"};bob={"x-ootd-dev-user":"bob@example.test"}
        created=client.post("/api/v1/wardrobe",headers=alice,json=item_payload(f"Alice-{uuid.uuid4().hex[:8]}"))
        assert created.status_code==201,created.text
        item_id=created.json()["id"]
        assert any(row["id"]==item_id for row in client.get("/api/v1/wardrobe",headers=alice).json())
        assert all(row["id"]!=item_id for row in client.get("/api/v1/wardrobe",headers=bob).json())
        assert client.get(f"/api/v1/wardrobe/{item_id}",headers=bob).status_code==404
        assert client.put(f"/api/v1/wardrobe/{item_id}",headers=bob,json=item_payload("被越权修改")).status_code==404

def test_production_requires_a_valid_signed_identity():
    previous_environment,previous_secret=settings.environment,settings.auth_shared_secret
    settings.environment="production";settings.auth_shared_secret="test-shared-secret"
    try:
        payload=base64.urlsafe_b64encode(json.dumps({"email":"signed@example.test","type":"access","exp":int(time.time())+60}).encode()).decode().rstrip("=")
        signature=hmac.new(settings.auth_shared_secret.encode(),payload.encode(),hashlib.sha256).hexdigest()
        with TestClient(app) as client:
            assert client.get("/api/v1/wardrobe").status_code==401
            signed=client.get("/api/v1/auth/me",headers={"authorization":f"Bearer {payload}.{signature}"})
            assert signed.status_code==200;signed_body=signed.json();assert signed_body["email"]=="signed@example.test"
            assert client.get("/api/v1/auth/me",headers={"authorization":f"Bearer {payload}.invalid"}).status_code==401
    finally:
        settings.environment,settings.auth_shared_secret=previous_environment,previous_secret

def test_image_analysis_prefills_wardrobe_fields():
    import io
    from PIL import Image
    image=Image.new("RGB",(40,40),(32,55,90));buffer=io.BytesIO();image.save(buffer,format="PNG")
    with TestClient(app) as client:
        result=client.post("/api/v1/wardrobe/analyze",files={"file":("藏青夹克.png",buffer.getvalue(),"image/png")})
        assert result.status_code==200,result.text
        body=result.json();assert body["category"]=="外套";assert body["wearing_layer"]=="外搭"
        assert body["color"]=="藏青";assert body["confidence"]["category"]>=.7

def test_outfit_analysis_has_safe_local_fallback_without_vision_model():
    import io
    from PIL import Image
    previous_key,previous_model=settings.openai_vision_api_key,settings.openai_vision_model
    settings.openai_vision_api_key=None;settings.openai_vision_model=None
    try:
        image=Image.new("RGB",(40,40),(30,30,30));buffer=io.BytesIO();image.save(buffer,format="PNG")
        with TestClient(app) as client:
            result=client.post("/api/v1/wardrobe/analyze-outfit",files={"file":("今日穿搭.png",buffer.getvalue(),"image/png")})
            assert result.status_code==200,result.text
            body=result.json();assert len(body["items"])==1
            assert body["generated_by"]=="local_single_item_fallback"
    finally:
        settings.openai_vision_api_key,settings.openai_vision_model=previous_key,previous_model

def test_product_link_import_rejects_private_networks():
    with TestClient(app) as client:
        result=client.post("/api/v1/wardrobe/import-link",data={"url":"http://127.0.0.1/private-product"})
        assert result.status_code==422
        assert "内网" in result.json()["detail"]

def test_upload_rejects_duplicate_name_even_when_color_differs():
    import io
    from PIL import Image
    image=Image.new("RGB",(24,24),(240,240,240));buffer=io.BytesIO();image.save(buffer,format="PNG")
    name=f"同名测试-{uuid.uuid4().hex[:8]}"
    with TestClient(app) as client:
        first=upload_wardrobe_item(client,buffer.getvalue(),name)
        assert first.status_code==201,first.text
        second=upload_wardrobe_item(client,buffer.getvalue(),name,category="外套",color="黑色")
        assert second.status_code==409
        assert second.json()["detail"]["code"]=="DUPLICATE_WARDROBE_ITEM_NAME"

def test_local_register_login_refresh_and_logout():
    email=f"local-{uuid.uuid4().hex[:10]}@example.test";password="safe-local-password-123"
    with TestClient(app) as client:
        registered=client.post("/api/v1/auth/register",json={"email":email,"password":password})
        assert registered.status_code==201,registered.text
        access=registered.json()["access_token"]
        me=client.get("/api/v1/auth/me",headers={"authorization":f"Bearer {access}"})
        assert me.status_code==200;assert me.json()["email"]==email
        profile=client.get("/api/v1/profile",headers={"authorization":f"Bearer {access}"}).json()
        assert profile["temperature_preference"]==""
        assert profile["preferred_styles"]==[] and profile["preferred_item_terms"]==[]
        assert profile["avoided_styles"]==[] and profile["avoided_item_terms"]==[]
        assert client.post("/api/v1/auth/login",json={"email":email,"password":"wrong-password"}).status_code==401
        logged_in=client.post("/api/v1/auth/login",json={"email":email,"password":password})
        assert logged_in.status_code==200
        refreshed=client.post("/api/v1/auth/refresh")
        assert refreshed.status_code==200;assert refreshed.json()["access_token"]
        assert client.post("/api/v1/auth/logout").status_code==204
        assert client.post("/api/v1/auth/refresh").status_code==401

def test_health_and_generate():
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code==200
        insights=client.get("/api/v1/wardrobe/insights-v2")
        assert insights.status_code==200,insights.text
        assert {"most_worn_item_ids","idle_item_ids","core_item_ids","isolated_item_ids","functional_gaps","color_distribution"}<=insights.json().keys()
        assert client.get("/api/v1/integrations").status_code==200
        r=client.post("/api/v1/outfits/generate",json={"occasion":"商务休闲","weather":{"city":"深圳市","district":"福田区","temperature_c":29,"feels_like_c":33,"temperature_min_c":25,"temperature_max_c":30,"rain_probability":.45,"wind_level":3.7,"condition":"多云"}})
        assert r.status_code==200,r.text;body=r.json();assert len(body["outfits"])==3;assert len(body["preview_task_ids"])==3
        assert "深圳市 福田区当日 25–30℃、当前 29℃、体感 33℃" in body["outfits"][0]["reason"]
        wardrobe={x["id"] for x in client.get("/api/v1/wardrobe").json()};assert all(set(o["item_ids"])<=wardrobe and o["outfit_id"] for o in body["outfits"])
        outfit=body["outfits"][0];replaced=None;target=None
        assert body["evidence_pack"][0]["dimensions"]
        assert {"claim","facts","source_refs","confidence","method"}<=body["evidence_pack"][0]["dimensions"][0].keys()
        stored_evidence=client.get(f"/api/v1/outfits/{outfit['outfit_id']}/evidence")
        assert stored_evidence.status_code==200
        assert stored_evidence.json()["dimensions"]
        for candidate_id in reversed(outfit["item_ids"]):
            attempt=client.post("/api/v1/outfits/replace-item",json={"outfit_id":outfit["outfit_id"],"item_id":candidate_id,"mode":"similar"})
            if attempt.status_code==201:replaced=attempt;target=candidate_id;break
        assert replaced is not None and target is not None
        assert target not in replaced.json()["item_ids"] and len(replaced.json()["item_ids"])==len(outfit["item_ids"])
        recent=client.get("/api/v1/outfits/recent",params={"limit":3})
        assert recent.status_code==200
        assert [row["kind"] for row in recent.json()]==["主推荐","舒适备选","风格备选"]
        first,second=body["outfits"][:2]
        assert client.post("/api/v1/feedback",json={"outfit_id":first["outfit_id"],"adopted":True,"replace_today":True}).status_code==201
        conflict=client.post("/api/v1/feedback",json={"outfit_id":second["outfit_id"],"adopted":True})
        assert conflict.status_code==409 and conflict.json()["detail"]["code"]=="today_outfit_exists"
        replaced=client.post("/api/v1/feedback",json={"outfit_id":second["outfit_id"],"adopted":True,"replace_today":True})
        assert replaced.status_code==201 and replaced.json()["replaced_today"] is True
        today=[row for row in client.get("/api/v1/calendar").json() if row["outfit_id"] in {first["outfit_id"],second["outfit_id"]}]
        assert [row["outfit_id"] for row in today]==[second["outfit_id"]]
        funnel=client.get("/api/v1/personalization/metrics").json()["funnel"]
        assert funnel["recommendation_batches"]>=1
        assert funnel["replacement_actions"]>=1
        assert funnel["adopted"]>=1
        assert 0<=funnel["adoption_rate"]<=1

def test_wardrobe_upload_edit_and_status_share_one_record():
    with TestClient(app) as client:
        original_name=f"测试白色平底鞋-{uuid.uuid4().hex[:8]}"
        created=upload_wardrobe_item(client,b"fake-image-bytes",original_name,category="鞋履",fit="常规",warmth_level=1,formality_level=3,seasons=["四季"],styles=["简约","通勤"],clean_status="可穿")
        assert created.status_code==201,created.text;item=created.json();item_id=item["id"];assert item["image_url"].startswith("/api/v1/assets/");assert item["image_asset_id"]
        fetched=client.get(f"/api/v1/wardrobe/{item_id}");assert fetched.status_code==200;assert fetched.json()["subcategory"]==original_name
        payload={k:item[k] for k in ["category","subcategory","colors","material_guess","material_confidence","pattern","fit","length","warmth_level","formality_level","styles","seasons","weather_constraints","clean_status","image_url"]};payload["subcategory"]=f"状态持久化平底鞋-{uuid.uuid4().hex[:8]}";payload["colors"]=["米白"]
        edited=client.put(f"/api/v1/wardrobe/{item_id}",json=payload);assert edited.status_code==200;assert edited.json()["colors"]==["米白"]
        changed=client.patch(f"/api/v1/wardrobe/{item_id}/status",params={"value":"待洗"});assert changed.status_code==200
        assert changed.json()["status"]=="待洗"
        assert client.get(f"/api/v1/wardrobe/{item_id}").json()["clean_status"]=="待洗"
        assert all(row["id"]!=item_id for row in client.get("/api/v1/wardrobe",params={"status":"可穿"}).json())
        invalid=client.patch(f"/api/v1/wardrobe/{item_id}/status",params={"value":"未知状态"})
        assert invalid.status_code==422

        # Re-entering the application lifespan must not silently reset persisted state.
        with TestClient(app) as restarted_client:
            persisted=restarted_client.get(f"/api/v1/wardrobe/{item_id}")
            assert persisted.status_code==200
            assert persisted.json()["clean_status"]=="待洗"
    with SessionLocal() as db:
        row=db.get(WardrobeItem,item_id)
        if row:
            asset=db.get(ImageAsset,row.image_asset_id);db.delete(row);db.commit()
            if asset:local_path(asset.object_key).unlink(missing_ok=True);db.delete(asset);db.commit()

def test_wardrobe_item_delete_soft_deletes_private_asset():
    with TestClient(app) as client:
        name=f"待删除单品-{uuid.uuid4().hex[:8]}"
        created=upload_wardrobe_item(client,b"fake-image-bytes",name,color="蓝色")
        assert created.status_code==201,created.text
        item=created.json()
        with SessionLocal() as db:image_path=local_path(db.get(ImageAsset,item["image_asset_id"]).object_key)
        assert image_path.exists()
        deleted=client.delete(f"/api/v1/wardrobe/{item['id']}")
        assert deleted.status_code==204
        assert client.get(f"/api/v1/wardrobe/{item['id']}").status_code==404
        assert image_path.exists()
        assert client.get(item["image_url"]).status_code==404
        with SessionLocal() as db:
            asset=db.get(ImageAsset,item["image_asset_id"]);assert asset.status=="pending_delete" and asset.deleted_at is not None
            image_path.unlink(missing_ok=True);db.delete(asset);db.commit()

def test_presigned_local_upload_creates_private_wardrobe_asset():
    content=b"signed-image-content";name=f"直传衬衫-{uuid.uuid4().hex[:8]}"
    with TestClient(app) as client:
        signed=client.post("/api/v1/uploads/sign",json={"filename":"shirt.png","content_type":"image/png","byte_size":len(content),"kind":"wardrobe"})
        assert signed.status_code==200,signed.text;ticket=signed.json()
        uploaded=client.put(ticket["upload_url"],content=content,headers={"Content-Type":"image/png"});assert uploaded.status_code==204,uploaded.text
        created=client.post("/api/v1/wardrobe/from-upload",json={"asset_id":ticket["asset_id"],"category":"上装","subcategory":name,"color":"白色"})
        assert created.status_code==201,created.text;item=created.json();assert item["image_asset_id"]==ticket["asset_id"]
        fetched=client.get(item["image_url"]);assert fetched.status_code==200 and fetched.content==content
        assert client.delete(f"/api/v1/wardrobe/{item['id']}").status_code==204
        with SessionLocal() as db:
            asset=db.get(ImageAsset,ticket["asset_id"]);path=local_path(asset.object_key);path.unlink(missing_ok=True);db.delete(asset);db.commit()
