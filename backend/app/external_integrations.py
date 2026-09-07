import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from .config import settings
from .models import AuthorizedIntegration


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.auth_shared_secret.encode()).digest())
    return Fernet(key)


def encrypt_credentials(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(value: str) -> dict:
    return json.loads(_fernet().decrypt(value.encode()).decode())


def oauth_state(user_id: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"uid": user_id, "exp": int(time.time()) + 600}).encode()).decode().rstrip("=")
    signature = hmac.new(settings.auth_shared_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_oauth_state(state: str) -> str:
    try:
        payload, supplied = state.split(".", 1)
        expected = hmac.new(settings.auth_shared_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected): raise ValueError("signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < int(time.time()): raise ValueError("expired")
        return data["uid"]
    except Exception as exc:
        raise ValueError("OAuth state 无效或已过期") from exc


def outlook_authorization_url(user_id: str) -> str:
    if not settings.microsoft_client_id or not settings.microsoft_client_secret:
        raise RuntimeError("尚未配置 Microsoft Client ID 和 Client Secret")
    query = urlencode({
        "client_id": settings.microsoft_client_id,
        "response_type": "code",
        "redirect_uri": settings.microsoft_redirect_uri,
        "response_mode": "query",
        "scope": "openid profile offline_access User.Read Calendars.Read",
        "state": oauth_state(user_id),
    })
    return f"https://login.microsoftonline.com/{settings.microsoft_tenant}/oauth2/v2.0/authorize?{query}"


async def exchange_outlook_code(code: str) -> dict:
    url = f"https://login.microsoftonline.com/{settings.microsoft_tenant}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, data={"client_id": settings.microsoft_client_id, "client_secret": settings.microsoft_client_secret, "code": code, "redirect_uri": settings.microsoft_redirect_uri, "grant_type": "authorization_code", "scope": "openid profile offline_access User.Read Calendars.Read"})
        response.raise_for_status()
        return response.json()


async def outlook_events(db, user_id: str, days: int = 14) -> list[dict]:
    row = db.scalar(select(AuthorizedIntegration).where(AuthorizedIntegration.user_id == user_id, AuthorizedIntegration.provider == "outlook", AuthorizedIntegration.status == "connected"))
    if not row or not row.encrypted_credential_ref: raise PermissionError("请先连接 Outlook 日历")
    token = decrypt_credentials(row.encrypted_credential_ref)
    if int(token.get("saved_at", 0)) + int(token.get("expires_in", 0)) - 60 <= int(time.time()):
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"https://login.microsoftonline.com/{settings.microsoft_tenant}/oauth2/v2.0/token", data={"client_id": settings.microsoft_client_id, "client_secret": settings.microsoft_client_secret, "refresh_token": token["refresh_token"], "grant_type": "refresh_token", "scope": "openid profile offline_access User.Read Calendars.Read"})
            response.raise_for_status(); token = response.json(); token["saved_at"] = int(time.time())
            row.encrypted_credential_ref = encrypt_credentials(token); db.commit()
    start = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    end = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")
    params = {"startDateTime": start, "endDateTime": end, "$select": "subject,start,end,location,isAllDay", "$orderby": "start/dateTime", "$top": "50"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get("https://graph.microsoft.com/v1.0/me/calendarView", params=params, headers={"Authorization": f"Bearer {token['access_token']}", "Prefer": 'outlook.timezone="China Standard Time"'})
        response.raise_for_status(); return response.json().get("value", [])


async def open_meteo_weather(city: str, latitude: float | None = None, longitude: float | None = None, district: str | None = None, forecast_date: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=12) as client:
        if latitude is None or longitude is None:
            geo = await client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "zh", "format": "json"}); geo.raise_for_status()
            places = geo.json().get("results", [])
            if not places: raise ValueError(f"没有找到城市：{city}")
            latitude,longitude=places[0]["latitude"],places[0]["longitude"]
        forecast = await client.get("https://api.open-meteo.com/v1/forecast", params={"latitude": latitude, "longitude": longitude, "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m", "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_probability_max,wind_speed_10m_max", "timezone": "auto", "forecast_days": 7}); forecast.raise_for_status()
    payload=forecast.json();current,daily=payload["current"],payload.get("daily",{})
    codes = {0:"晴",1:"大致晴朗",2:"多云",3:"阴",45:"有雾",48:"雾凇",51:"毛毛雨",53:"毛毛雨",55:"较强毛毛雨",61:"小雨",63:"中雨",65:"大雨",71:"小雪",73:"中雪",75:"大雪",80:"阵雨",81:"阵雨",82:"强阵雨",95:"雷雨"}
    dates=daily.get("time",[]);index=dates.index(forecast_date) if forecast_date in dates else 0
    is_today=not forecast_date or forecast_date==dates[0]
    temperature=current["temperature_2m"] if is_today else (daily["temperature_2m_max"][index]+daily["temperature_2m_min"][index])/2
    feels=current["apparent_temperature"] if is_today else (daily["apparent_temperature_max"][index]+daily["apparent_temperature_min"][index])/2
    code=current["weather_code"] if is_today else daily["weather_code"][index]
    wind=current["wind_speed_10m"] if is_today else daily["wind_speed_10m_max"][index]
    return {"date":dates[index] if dates else forecast_date,"city":city,"district":district,"temperature_c":round(temperature,1),"feels_like_c":round(feels,1),"temperature_max_c":daily["temperature_2m_max"][index],"temperature_min_c":daily["temperature_2m_min"][index],"rain_probability":(daily.get("precipitation_probability_max") or [0])[index]/100,"wind_level":wind,"condition":codes.get(code,"天气变化")}
