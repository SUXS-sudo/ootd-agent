import base64
import hashlib
import hmac
import json
import time
import secrets
from datetime import timedelta
from .time_utils import datetime
from contextvars import ContextVar

from fastapi import HTTPException, Request

from .config import settings
from .database import SessionLocal
from .models import AuthSession, User, UserProfile


_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def decode_token(token: str, expected_type: str = "access") -> dict:
    if settings.environment not in {"development", "test"} and settings.auth_shared_secret == "development-only-change-me":
        raise HTTPException(503, "生产环境尚未配置 AUTH_SHARED_SECRET")
    try:
        encoded_payload, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.auth_shared_secret.encode(),
            encoded_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("signature mismatch")
        padded = encoded_payload + "=" * (-len(encoded_payload) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("token expired")
        if not payload.get("email"):
            raise ValueError("missing identity")
        if payload.get("type") != expected_type:
            raise ValueError("wrong token type")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "登录凭证无效或已过期") from exc


def _stable_user_id(email: str) -> str:
    return "u_" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:20]


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if len(password) < 8:raise HTTPException(422,"密码至少需要 8 个字符")
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    return base64.urlsafe_b64encode(digest).decode(),base64.urlsafe_b64encode(salt).decode()


def verify_password(password: str, encoded_hash: str, encoded_salt: str) -> bool:
    try:
        actual,_=hash_password(password,base64.urlsafe_b64decode(encoded_salt.encode()))
        return hmac.compare_digest(actual,encoded_hash)
    except (ValueError,TypeError):return False


def issue_token(email: str, token_type: str, lifetime_seconds: int, session_id: str | None = None) -> str:
    payload={"email":email,"type":token_type,"exp":int(time.time())+lifetime_seconds}
    if session_id:payload["sid"]=session_id
    encoded=base64.urlsafe_b64encode(json.dumps(payload,separators=(",",":")).encode()).decode().rstrip("=")
    signature=hmac.new(settings.auth_shared_secret.encode(),encoded.encode(),hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def create_local_session(db, user: User) -> tuple[str,str]:
    session_id="session_"+secrets.token_urlsafe(24)
    db.add(AuthSession(id=session_id,user_id=user.id,expires_at=datetime.utcnow()+timedelta(days=30)))
    db.commit()
    return issue_token(user.email,"access",900),issue_token(user.email,"refresh",30*24*3600,session_id)


def _ensure_user(email: str, display_name: str | None = None) -> str:
    user_id = _stable_user_id(email)
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            db.add(User(id=user_id, email=email.strip().lower()))
            db.add(UserProfile(user_id=user_id))
            db.commit()
    return user_id


async def bind_current_user(request: Request) -> str:
    if request.url.path.endswith("/health"):
        user_id = settings.demo_user_id
    else:
        if request.url.path in {"/api/v1/auth/register","/api/v1/auth/login","/api/v1/auth/refresh","/api/v1/auth/logout","/api/v1/integrations/outlook/callback"}:
            user_id=settings.demo_user_id
            _current_user_id.set(user_id)
            return user_id
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            payload = decode_token(authorization[7:].strip())
            user_id = _ensure_user(payload["email"], payload.get("name"))
        elif request.cookies.get("ootd_access"):
            payload = decode_token(request.cookies["ootd_access"])
            user_id = _ensure_user(payload["email"], payload.get("name"))
        elif settings.environment in {"development", "test"}:
            dev_identity = request.headers.get("x-ootd-dev-user")
            user_id = _ensure_user(dev_identity) if dev_identity else settings.demo_user_id
        else:
            raise HTTPException(401, "请先登录")
    _current_user_id.set(user_id)
    return user_id


def current_user_id() -> str:
    user_id = _current_user_id.get()
    if not user_id:
        raise HTTPException(401, "请先登录")
    return user_id
