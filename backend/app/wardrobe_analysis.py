import base64
import io
import json
import re

from PIL import Image, ImageOps
from openai import AsyncOpenAI

from .config import settings


COLOR_REFERENCES = {
    "黑色": (30, 30, 30), "白色": (238, 238, 232), "灰色": (135, 135, 135),
    "米白": (224, 211, 178), "棕色": (120, 78, 50), "藏青": (35, 52, 82),
    "蓝色": (65, 115, 170), "绿色": (70, 120, 75), "红色": (165, 55, 55),
    "粉色": (220, 145, 160), "紫色": (125, 85, 145), "黄色": (215, 180, 65),
}


def _category_from_name(name: str) -> tuple[str, str, float]:
    normalized = re.sub(r"[_-]+", " ", name.rsplit(".", 1)[0]).strip()
    rules = [
        (r"鞋|shoe|sneaker|boot|loafer", "鞋履"), (r"包|bag|tote", "包袋"),
        (r"连衣裙|dress", "连衣裙"), (r"裤|半身裙|pants|jeans|skirt", "下装"),
        (r"外套|夹克|西装|开衫|coat|jacket|blazer|cardigan", "外套"),
        (r"帽|围巾|项链|耳环|belt|scarf|hat", "配饰"),
        (r"衬衫|上衣|针织|T恤|shirt|sweater|top", "上装"),
    ]
    category = next((value for pattern, value in rules if re.search(pattern, normalized, re.I)), "上装")
    confidence = .88 if any(re.search(pattern, normalized, re.I) for pattern, _ in rules) else .42
    return category, normalized or "新衣物", confidence


def _dominant_color(image: Image.Image) -> tuple[str, float]:
    source = ImageOps.exif_transpose(image).convert("RGBA")
    background = Image.new("RGBA", source.size, "white")
    background.alpha_composite(source)
    sample = background.convert("RGB")
    sample.thumbnail((96, 96))
    pixels = [pixel for pixel in sample.getdata() if max(pixel)-min(pixel) > 8 or sum(pixel) < 690]
    if not pixels: return "白色", .45
    pixels.sort(key=lambda pixel: sum(pixel))
    middle = pixels[len(pixels)//5:len(pixels)*4//5] or pixels
    rgb = tuple(sum(pixel[i] for pixel in middle)//len(middle) for i in range(3))
    ranked = sorted(COLOR_REFERENCES.items(), key=lambda row: sum((rgb[i]-row[1][i])**2 for i in range(3)))
    distance = sum((rgb[i]-ranked[0][1][i])**2 for i in range(3)) ** .5
    return ranked[0][0], max(.35, min(.9, 1-distance/300))


def analyze_wardrobe_image(content: bytes, filename: str) -> dict:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            color, color_confidence = _dominant_color(image)
    except Exception as exc:
        raise ValueError("无法读取图片内容，请选择有效的 JPG、PNG 或 WebP") from exc
    category, name, category_confidence = _category_from_name(filename)
    wearing_layer = "外搭" if category == "外套" else "内搭" if re.search(r"打底|吊带|背心", name) else "主上装"
    return {"category":category,"subcategory":name,"color":color,"material_guess":[],"material_confidence":0,"pattern":"待确认","length":"待确认","weather_constraints":[],"wearing_layer":wearing_layer,"fit":"常规","warmth_level":2,"formality_level":3,"seasons":["四季"],"styles":[],"confidence":{"category":category_confidence,"color":round(color_confidence,2)},"generated_by":"local_image_rules"}


async def analyze_outfit_items(content: bytes, filename: str) -> dict:
    """Turn one worn-outfit photo into confirmable wardrobe item drafts."""
    fallback = analyze_wardrobe_image(content, filename)
    separate_vision_provider = bool(settings.openai_vision_base_url and settings.openai_vision_base_url.rstrip("/") != settings.openai_base_url.rstrip("/"))
    key = settings.openai_vision_api_key if separate_vision_provider else (settings.openai_vision_api_key or settings.openai_api_key)
    model = settings.openai_vision_model
    if not key or not model:
        return {
            "items": [fallback],
            "generated_by": "local_single_item_fallback",
            "notice": "未配置视觉模型，已先生成一个可编辑草稿；配置视觉模型后可从整身照拆出多个单品。",
        }

    mime = {".png": "image/png", ".webp": "image/webp"}.get(
        f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else "", "image/jpeg"
    )
    image_url = f"data:{mime};base64,{base64.b64encode(content).decode()}"
    schema = {
        "items": [{
            "category": "上装/下装/连衣裙/外套/鞋履/包袋/配饰",
            "subcategory": "简短具体名称",
            "color": "主色",
            "material_guess": ["棉"],
            "material_confidence": 0.7,
            "pattern": "纯色/条纹/格纹/印花/图案/其他/待确认",
            "length": "短款/常规/中长/长款/待确认",
            "weather_constraints": ["不适合雨天"],
            "wearing_layer": "内搭/主上装/外搭/不可叠穿",
            "fit": "修身/常规/宽松",
            "warmth_level": 2,
            "formality_level": 3,
            "seasons": ["春", "秋"],
            "styles": ["简约"],
            "confidence": {"category": 0.9, "color": 0.8},
            "bounding_box": [120, 80, 880, 520],
        }]
    }
    prompt = (
        "识别照片中当前主体人物实际穿戴的可独立管理单品。不要识别其他人物、人体、背景或被完全遮挡的衣物；"
        "鞋按一双计，最多返回8件。材质只能依据原始照片中可见的纹理推测，并给出0到1的置信度；"
        "看不清的材质返回空数组，其他看不清的属性填写待确认，不要根据生成图或常识编造。严格返回JSON："
        + json.dumps(schema, ensure_ascii=False)
    )
    client = AsyncOpenAI(api_key=key, base_url=settings.openai_vision_base_url or settings.openai_base_url)
    request = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
        ]}],
        "temperature": .1, "max_tokens": 3000,
    }
    if model.lower().startswith("glm-"):
        request["extra_body"] = {"thinking": {"type": "disabled"}}
    else:
        request["response_format"] = {"type": "json_object"}
    response = await client.chat.completions.create(**request)
    raw = response.choices[0].message.content or ""
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("视觉模型未返回可识别的单品列表")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        reason = "模型输出被截断" if finish_reason == "length" else "模型返回的 JSON 格式不完整"
        raise ValueError(f"{reason}，请重试一次") from exc
    allowed = {"上装", "下装", "连衣裙", "外套", "鞋履", "包袋", "配饰"}
    items = []
    for item in (data.get("items") or [])[:8]:
        if not isinstance(item, dict) or item.get("category") not in allowed:
            continue
        confidence = item.get("confidence") or {}
        result_item = {
            "category": item["category"],
            "subcategory": str(item.get("subcategory") or "待确认单品")[:60],
            "color": str(item.get("color") or "未标注")[:24],
            "material_guess": [str(x)[:24] for x in (item.get("material_guess") or [])[:4]],
            "material_confidence": max(0, min(1, float(item.get("material_confidence", 0)))),
            "pattern": str(item.get("pattern") or "待确认")[:24],
            "length": str(item.get("length") or "待确认")[:24],
            "weather_constraints": [str(x)[:40] for x in (item.get("weather_constraints") or [])[:5]],
            "wearing_layer": item.get("wearing_layer") or ("外搭" if item["category"] == "外套" else "主上装"),
            "fit": item.get("fit") or "常规",
            "warmth_level": max(0, min(5, int(item.get("warmth_level", 2)))),
            "formality_level": max(0, min(5, int(item.get("formality_level", 3)))),
            "seasons": list(item.get("seasons") or ["四季"]),
            "styles": list(item.get("styles") or []),
            "confidence": {
                "category": float(confidence.get("category", .6)),
                "color": float(confidence.get("color", .6)),
            },
            "generated_by": "vision_outfit_extraction",
        }
        box = item.get("bounding_box")
        if isinstance(box, list) and len(box) == 4:
            try:
                with Image.open(io.BytesIO(content)) as source:
                    source = ImageOps.exif_transpose(source).convert("RGB")
                    left, top, right, bottom = [max(0, min(1000, int(value))) for value in box]
                    if right > left and bottom > top:
                        padding = 25
                        crop_box = (
                            max(0, (left-padding)*source.width//1000), max(0, (top-padding)*source.height//1000),
                            min(source.width, (right+padding)*source.width//1000), min(source.height, (bottom+padding)*source.height//1000),
                        )
                        cropped = source.crop(crop_box);output = io.BytesIO();cropped.save(output, format="JPEG", quality=90)
                        result_item["crop_image_data"] = base64.b64encode(output.getvalue()).decode()
                        result_item["crop_mime_type"] = "image/jpeg"
            except (OSError, TypeError, ValueError):
                pass
        items.append(result_item)
    if not items:
        raise ValueError("没有在照片主体上识别到可靠的服饰单品")
    return {"items": items, "generated_by": "vision_outfit_extraction", "notice": ""}
