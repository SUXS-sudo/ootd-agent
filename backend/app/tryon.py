import base64
import mimetypes
import re
import uuid
from pathlib import Path

import httpx
from fastapi import HTTPException, UploadFile

from .config import settings


GENERATED_DIR = Path(__file__).resolve().parents[1] / "generated"


def tryon_task_payload(person_asset_id: str, outfit_id: str, views: list[str], outerwear_state: str) -> dict:
    return {
        "task_id": f"tryon_{uuid.uuid4().hex[:10]}",
        "kind": "identity_preserving_tryon",
        "person_asset_id": person_asset_id,
        "outfit_id": outfit_id,
        "views": views,
        "outerwear_state": outerwear_state,
        "invariants": ["identity", "pose", "body_proportion", "garment_color", "garment_pattern", "garment_structure"],
        "quality_gates": {"identity": .82, "proportion": .85, "garment_color": .9, "extra_limb": 0},
        "fallback": "real_item_collage",
        "disclaimer": "颜色和整体轮廓参考价值较高；面料垂坠与裤长效果仅供参考。",
    }


def _data_url(data: bytes, content_type: str | None, filename: str | None) -> str:
    mime = content_type or mimetypes.guess_type(filename or "image.jpg")[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _find_image_value(payload: dict) -> str | None:
    choices = payload.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        for key in ("images", "image", "output_images"):
            value = message.get(key)
            if isinstance(value, list) and value:
                item = value[0]
                if isinstance(item, str):
                    return item
                if isinstance(item, dict):
                    return item.get("url") or item.get("image_url") or item.get("b64_json")
            if isinstance(value, str):
                return value
        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                value = item.get("image_url") or item.get("url") or item.get("b64_json")
                if isinstance(value, dict):
                    value = value.get("url")
                if value:
                    return value
                if item.get("type") in {"text", "output_text"}:
                    content = item.get("text", "")
                    break
        if isinstance(content, str):
            markdown = re.search(r"!\[[^]]*\]\((https?://[^)]+|data:image/[^)]+)\)", content)
            if markdown:
                return markdown.group(1)
            url = re.search(r"https?://\S+", content)
            if url:
                return url.group(0).rstrip(".,)")
            data_uri = re.search(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", content)
            if data_uri:
                return data_uri.group(0)
    data = payload.get("data") or []
    if data and isinstance(data[0], dict):
        return data[0].get("url") or data[0].get("b64_json")
    return None


async def generate_tryon(person: UploadFile, garment: UploadFile, prompt: str | None = None) -> dict:
    image_api_key = settings.openai_image_api_key or settings.openai_api_key
    image_base_url = settings.openai_image_base_url or settings.openai_base_url
    if not image_api_key:
        raise HTTPException(503, "OPENAI_IMAGE_API_KEY is not configured")
    person_bytes = await person.read()
    garment_bytes = await garment.read()
    if not person_bytes or not garment_bytes:
        raise HTTPException(422, "人物照片和衣服参考图不能为空")
    if len(person_bytes) > 12 * 1024 * 1024 or len(garment_bytes) > 12 * 1024 * 1024:
        raise HTTPException(413, "单张图片不能超过 12MB")

    instruction = prompt or (
        "你是专业虚拟试衣图片编辑器。第一张图片是人物原图，第二张图片是衣服参考图。"
        "保持第一张图中人物的脸部身份、发型、身体比例、姿势、手部、相机角度和背景不变；"
        "把参考图中每一件独立单品都应用到人物身上，不得省略鞋履、包袋或其他配饰；保留服装颜色、图案、结构和材质细节。"
        "鞋履必须替换原鞋，画面从头到脚完整构图并清楚显示双脚；包袋必须自然肩背、斜挎或手提，允许为持包轻微调整手臂。"
        "输出一张写实、自然、完整的全身换装照片，不要文字、拼图、水印、额外单品或前后对比排版。"
    )
    url = f"{image_base_url.rstrip('/')}{settings.openai_image_endpoint}"
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            if settings.openai_image_endpoint.endswith("/chat/completions"):
                body = {
                    "model": settings.openai_image_model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": _data_url(person_bytes, person.content_type, person.filename)}},
                        {"type": "image_url", "image_url": {"url": _data_url(garment_bytes, garment.content_type, garment.filename)}},
                    ]}],
                    "size": settings.openai_image_size,
                    "stream": False,
                }
                response = await client.post(url, headers={"Authorization": f"Bearer {image_api_key}"}, json=body)
            else:
                files = [
                    ("image[]", (person.filename or "person.jpg", person_bytes, person.content_type or "image/jpeg")),
                    ("image[]", (garment.filename or "garment.jpg", garment_bytes, garment.content_type or "image/jpeg")),
                ]
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {image_api_key}"},
                    data={"model": settings.openai_image_model, "prompt": instruction, "size": settings.openai_image_size},
                    files=files,
                )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1200]
        raise HTTPException(exc.response.status_code, f"图片模型请求失败：{detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"图片模型响应异常：{str(exc)[:500]}") from exc

    image_value = _find_image_value(payload)
    if not image_value:
        raise HTTPException(502, f"图片模型未返回可识别的图片：{str(payload)[:1200]}")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"tryon-{uuid.uuid4().hex}.png"
    output_path = GENERATED_DIR / filename
    if image_value.startswith("data:image/"):
        _, encoded = image_value.split(",", 1)
        output_path.write_bytes(base64.b64decode(encoded))
    elif image_value.startswith("http://") or image_value.startswith("https://"):
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            image_response = await client.get(image_value)
            image_response.raise_for_status()
            output_path.write_bytes(image_response.content)
    else:
        try:
            output_path.write_bytes(base64.b64decode(image_value))
        except ValueError as exc:
            raise HTTPException(502, "图片模型返回了无法解析的图片数据") from exc

    return {
        "status": "completed",
        "model": settings.openai_image_model,
        "result_url": f"/generated/{filename}",
    }


async def generate_clean_garment(file: UploadFile, name: str, category: str, color: str) -> dict:
    """Create a person-free catalog view from a real garment reference crop."""
    image_api_key = settings.openai_image_api_key or settings.openai_api_key
    image_base_url = settings.openai_image_base_url or settings.openai_base_url
    if not image_api_key:
        raise HTTPException(503, "OPENAI_IMAGE_API_KEY is not configured")
    content = await file.read()
    if not content:
        raise HTTPException(422, "衣物参考图不能为空")
    if len(content) > 12 * 1024 * 1024:
        raise HTTPException(413, "衣物参考图不能超过 12MB")
    instruction = (
        f"参考图中目标单品是：{color}{name}，品类：{category}。生成一张仅展示这件真实单品的电商平铺/隐形衣架商品图。"
        "必须忠实保留参考图里可见的颜色、花纹、面料纹理、领型、袖型、门襟、纽扣、口袋、长度和版型；"
        "去除人物、皮肤、脸、头发、手脚、手机、包带遮挡（目标若不是包）、其他衣物及环境背景。"
        "把目标单品自然整理完整并居中放置在纯白背景上，四周留白，正面视角，柔和均匀棚拍光。"
        "不要模特、人体、人体局部、衣架、文字、标签、logo、水印、拼图、搭配建议或额外物品。"
        "若被遮挡区域无法确定，只做最保守、与可见结构连续一致的补全，不增加装饰和设计细节。"
    )
    url = f"{image_base_url.rstrip('/')}{settings.openai_image_endpoint}"
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            if settings.openai_image_endpoint.endswith("/chat/completions"):
                response = await client.post(url, headers={"Authorization": f"Bearer {image_api_key}"}, json={
                    "model": settings.openai_image_model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": _data_url(content, file.content_type, file.filename)}},
                    ]}], "size": "1024x1024", "stream": False,
                })
            else:
                response = await client.post(url, headers={"Authorization": f"Bearer {image_api_key}"},
                    data={"model": settings.openai_image_model, "prompt": instruction, "size": "1024x1024"},
                    files={"image": (file.filename or "garment.jpg", content, file.content_type or "image/jpeg")})
            response.raise_for_status();payload=response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, f"单品图生成失败：{exc.response.text[:1200]}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"单品图生成响应异常：{str(exc)[:500]}") from exc
    image_value = _find_image_value(payload)
    if not image_value:
        raise HTTPException(502, "图片模型未返回单品图")
    GENERATED_DIR.mkdir(parents=True, exist_ok=True);filename=f"garment-{uuid.uuid4().hex}.png";output_path=GENERATED_DIR/filename
    if image_value.startswith("data:image/"):
        output_path.write_bytes(base64.b64decode(image_value.split(",",1)[1]))
    elif image_value.startswith("http://") or image_value.startswith("https://"):
        async with httpx.AsyncClient(timeout=120,follow_redirects=True) as client:
            downloaded=await client.get(image_value);downloaded.raise_for_status();output_path.write_bytes(downloaded.content)
    else:
        try:output_path.write_bytes(base64.b64decode(image_value))
        except ValueError as exc:raise HTTPException(502,"图片模型返回了无法解析的单品图") from exc
    return {"status":"completed","model":settings.openai_image_model,"result_url":f"/generated/{filename}"}
