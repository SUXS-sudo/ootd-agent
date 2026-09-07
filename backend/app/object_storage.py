from __future__ import annotations

import hashlib
from pathlib import Path

from .config import BACKEND_DIR, settings


LOCAL_ASSET_DIR = BACKEND_DIR / "generated" / "assets"


def _s3_client():
    import boto3

    if not settings.storage_endpoint_url or not settings.storage_access_key_id or not settings.storage_secret_access_key:
        raise RuntimeError("R2/S3 storage credentials are incomplete")
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url,
        aws_access_key_id=settings.storage_access_key_id,
        aws_secret_access_key=settings.storage_secret_access_key,
        region_name=settings.storage_region,
    )


def local_path(object_key: str) -> Path:
    target = (LOCAL_ASSET_DIR / object_key).resolve()
    root = LOCAL_ASSET_DIR.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Invalid object key")
    return target


def create_upload_url(asset_id: str, object_key: str, content_type: str) -> str:
    if settings.storage_backend == "local":
        return f"/api/v1/uploads/direct/{asset_id}"
    return _s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.storage_bucket, "Key": object_key, "ContentType": content_type},
        ExpiresIn=settings.storage_upload_url_ttl_seconds,
    )


def put_bytes(object_key: str, content: bytes, content_type: str) -> None:
    if settings.storage_backend == "local":
        path = local_path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return
    _s3_client().put_object(Bucket=settings.storage_bucket, Key=object_key, Body=content, ContentType=content_type)


def get_bytes(object_key: str) -> bytes:
    if settings.storage_backend == "local":
        return local_path(object_key).read_bytes()
    return _s3_client().get_object(Bucket=settings.storage_bucket, Key=object_key)["Body"].read()


def object_metadata(object_key: str) -> dict:
    if settings.storage_backend == "local":
        path = local_path(object_key)
        if not path.is_file():
            raise FileNotFoundError(object_key)
        return {"ContentLength": path.stat().st_size}
    return _s3_client().head_object(Bucket=settings.storage_bucket, Key=object_key)


def probe_object(object_key: str) -> bool | None:
    """Return True/False for present/missing and None when storage is unavailable."""
    try:
        object_metadata(object_key)
        return True
    except FileNotFoundError:
        return False
    except RuntimeError:
        return None
    except Exception as exc:
        response = getattr(exc, "response", {}) or {}
        code = str((response.get("Error") or {}).get("Code", ""))
        status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return False
        return None


def create_read_url(object_key: str) -> str:
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.storage_bucket, "Key": object_key},
        ExpiresIn=settings.storage_read_url_ttl_seconds,
    )


def delete_object(object_key: str) -> None:
    if settings.storage_backend == "local":
        local_path(object_key).unlink(missing_ok=True)
        return
    _s3_client().delete_object(Bucket=settings.storage_bucket, Key=object_key)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
