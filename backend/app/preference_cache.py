import json
import time
from types import SimpleNamespace

from redis import Redis
from sqlalchemy import select

from .config import settings
from .models import ContextProfile, UserProfile

_client: Redis | None = None
_retry_after = 0.0
PROFILE_FIELDS = ("user_id","height_cm","temperature_preference","preferred_styles","avoided_styles","preferred_item_terms","avoided_item_terms","preferred_colors","avoided_colors","restrictions","visual_goals","photo_retention_consent")

def _redis() -> Redis | None:
    global _client, _retry_after
    if time.monotonic() < _retry_after:return None
    if _client is None:_client=Redis.from_url(settings.redis_url,decode_responses=True,socket_connect_timeout=.15,socket_timeout=.15)
    try:_client.ping();return _client
    except Exception:_retry_after=time.monotonic()+30;return None

def _get(key:str):
    client=_redis()
    if not client:return None
    try:
        value=client.get(key);return json.loads(value) if value else None
    except Exception:return None

def _set(key:str,value:dict,ttl:int):
    client=_redis()
    if client:
        try:client.setex(key,ttl,json.dumps(value,ensure_ascii=False))
        except Exception:pass

def recommendation_profile(db,user_id:str):
    key=f"ootd:preference:{user_id}:profile";cached=_get(key)
    if cached:return SimpleNamespace(**cached)
    row=db.get(UserProfile,user_id)
    if not row:return None
    payload={field:getattr(row,field,None) for field in PROFILE_FIELDS};_set(key,payload,settings.preference_cache_ttl_seconds)
    return row

def context_preferences(db,user_id:str,context_key:str) -> dict | None:
    key=f"ootd:preference:{user_id}:context:{context_key}";cached=_get(key)
    if cached:return cached
    row=db.scalar(select(ContextProfile).where(ContextProfile.user_id==user_id,ContextProfile.context_key==context_key))
    if not row:return None
    payload={"weights":row.weights,"preferences":row.preferences,"sample_count":row.sample_count};_set(key,payload,settings.preference_cache_ttl_seconds);return payload

def cache_styling_session(user_id:str,session_id:str,payload:dict):
    _set(f"ootd:session:{user_id}:{session_id}",payload,settings.styling_session_ttl_seconds)

def load_styling_session(user_id:str,session_id:str):
    return _get(f"ootd:session:{user_id}:{session_id}")

def invalidate_preferences(user_id:str,context_key:str|None=None):
    client=_redis()
    if not client:return
    try:
        keys=[f"ootd:preference:{user_id}:profile"]
        if context_key:keys.append(f"ootd:preference:{user_id}:context:{context_key}")
        else:keys.extend(client.scan_iter(match=f"ootd:preference:{user_id}:context:*"))
        if keys:client.delete(*keys)
    except Exception:pass
