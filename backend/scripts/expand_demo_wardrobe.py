"""Idempotently expand the demo user's wardrobe to 50 items per category."""

from collections import Counter
import hashlib
from itertools import cycle
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import WardrobeItem


TARGET = 50
PUBLIC_CLOTHES = Path(__file__).resolve().parents[2] / "public" / "clothes"
CATEGORY_KEYS = {
    "上装": "top",
    "下装": "bottom",
    "连衣裙": "dress",
    "外套": "outer",
    "鞋履": "shoes",
    "包袋": "bag",
    "配饰": "accessory",
}

TEMPLATES = {
    "上装": [
        ("米白针织上衣", "米白", "/clothes/item_1802-cream-knit.png", ["简约", "通勤"], ["秋", "冬"]),
        ("雾霾蓝棉质衬衫", "雾霾蓝", "/clothes/item_2204-misty-blue-shirt.png", ["通勤"], ["春", "秋"]),
        ("豆沙粉衬衫", "豆沙粉", "/clothes/item_6020-pink-blouse.png", ["温柔", "通勤"], ["春", "秋"]),
        ("酒红针织开衫", "酒红", "/clothes/item_6050-burgundy-cardigan.png", ["复古", "通勤"], ["秋", "冬"]),
        ("蓝色连帽卫衣", "蓝色", "/clothes/item_7020-blue-hoodie.png", ["休闲", "运动"], ["春", "秋"]),
        ("白色亚麻衬衫", "白色", "/clothes/item_7030-white-linen-shirt.png", ["简约", "度假"], ["春", "夏"]),
    ],
    "下装": [
        ("深灰直筒西裤", "深灰", "/clothes/item_3301-dark-gray-trousers.png", ["通勤"], ["四季"]),
        ("卡其阔腿裤", "卡其", "/clothes/item_3310-khaki-trousers.png", ["简约", "通勤"], ["春", "秋"]),
        ("森林绿半身裙", "森林绿", "/clothes/item_6030-forest-skirt.png", ["优雅", "复古"], ["春", "秋"]),
        ("藏青西裤", "藏青", "/clothes/item_6060-navy-trousers.png", ["通勤"], ["四季"]),
        ("酒红缎面半身裙", "酒红", "/clothes/item_7040-burgundy-skirt.png", ["优雅"], ["春", "夏", "秋"]),
        ("黑色牛仔裤", "黑色", "/clothes/item_7050-black-jeans.png", ["休闲"], ["四季"]),
        ("深靛蓝直筒牛仔裤", "深靛蓝", "/clothes/item_8204-indigo-jeans.png", ["休闲", "简约"], ["四季"]),
    ],
    "连衣裙": [
        ("豆沙粉裹身连衣裙", "豆沙粉", "/clothes/item_8202-dusty-rose-wrap-dress.png", ["优雅", "约会"], ["春", "夏"]),
    ],
    "外套": [
        ("藏青短款夹克", "藏青", "/clothes/item_2088-navy-jacket.png", ["休闲", "通勤"], ["春", "秋"]),
        ("驼色长款大衣", "驼色", "/clothes/item_6010-camel-coat.png", ["通勤", "经典"], ["秋", "冬"]),
        ("炭灰西装", "炭灰", "/clothes/item_7010-charcoal-blazer.png", ["商务", "通勤"], ["四季"]),
        ("绿色防雨外套", "绿色", "/clothes/item_7080-green-rain-jacket.png", ["户外", "休闲"], ["春", "秋"]),
        ("黑色修身西装", "黑色", "/clothes/item_8201-black-blazer.png", ["商务", "通勤"], ["四季"]),
        ("橄榄绿轻量雨衣", "橄榄绿", "/clothes/item_8203-olive-rain-jacket.png", ["户外", "休闲"], ["春", "秋"]),
    ],
    "鞋履": [
        ("白色运动鞋", "白色", "/clothes/item_4011-white-sneakers.png", ["休闲", "运动"], ["四季"]),
        ("棕色乐福鞋", "棕色", "/clothes/item_4018-brown-loafers.png", ["通勤", "复古"], ["四季"]),
        ("黑色短靴", "黑色", "/clothes/item_6040-black-boots.png", ["通勤", "酷感"], ["秋", "冬"]),
        ("奶油色帆布鞋", "奶油色", "/clothes/item_7060-cream-sneakers.png", ["休闲"], ["春", "夏", "秋"]),
        ("酒红玛丽珍鞋", "酒红", "/clothes/item_7090-burgundy-mary-jane.png", ["复古", "通勤"], ["四季"]),
        ("杏仁米色低跟鞋", "杏仁米", "/clothes/item_7100-beige-slingback.png", ["优雅", "通勤"], ["春", "夏"]),
        ("米白芭蕾平底鞋", "米白", "/clothes/item-test-ivory-ballet-flats.png", ["温柔", "通勤"], ["春", "夏"]),
    ],
    "包袋": [
        ("焦糖色托特包", "焦糖色", "/clothes/item_7070-caramel-bag.png", ["通勤", "经典"], ["四季"]),
    ],
    "配饰": [
        ("米灰日常配饰", "米灰", "/clothes/item-demo-accessory.svg", ["简约"], ["四季"]),
    ],
}

COLOR_HEX = {
    "米白": "#e9dfcb", "雾霾蓝": "#8197a3", "豆沙粉": "#bd7f83", "酒红": "#722f37",
    "蓝色": "#5579a5", "白色": "#eeeae1", "深灰": "#55565b", "卡其": "#ae9165",
    "森林绿": "#416453", "藏青": "#263a55", "黑色": "#29292c", "深靛蓝": "#314b69",
    "驼色": "#aa7c51", "炭灰": "#48494d", "绿色": "#55745c", "橄榄绿": "#657052",
    "棕色": "#704a36", "奶油色": "#e5d4af", "杏仁米": "#d2b996", "焦糖色": "#a96836",
    "米灰": "#aaa294",
}


def _svg_art(item: WardrobeItem) -> str:
    """Create a category-aware illustration; every demo item gets its own visual variant."""
    digest = hashlib.sha256(item.id.encode()).digest()
    base = COLOR_HEX.get(item.colors[0] if item.colors else "", "#8b8175")
    accents = ["#efe8dc", "#d6b98c", "#93a99b", "#c88e89", "#7f91a8", "#b7a58d"]
    accent = accents[digest[0] % len(accents)]
    shift = digest[1] % 25 - 12
    stripe = 10 + digest[2] % 18
    shapes = {
        "上装": f'<path d="M190 190 L260 {135+shift} H380 L450 190 406 270 370 248 V480 H270 V248 L234 270 Z"/>',
        "下装": f'<path d="M246 145 H394 L420 490 H338 L320 278 302 490 H220 Z"/>',
        "连衣裙": f'<path d="M260 138 H380 L402 216 368 238 430 500 H210 L272 238 238 216 Z"/>',
        "外套": f'<path d="M210 176 L278 {132+shift} H362 L430 176 398 294 366 270 386 492 H254 L274 270 242 294 Z"/>',
        "鞋履": f'<path d="M122 350 Q210 330 270 260 L342 294 318 366 500 398 Q526 410 512 448 H120 Q96 422 122 350 Z"/>',
        "包袋": f'<rect x="168" y="226" width="304" height="244" rx="{28+digest[3]%30}"/><path d="M246 230 Q246 132 320 132 Q394 132 394 230" fill="none" stroke-width="24"/>',
        "配饰": f'<circle cx="320" cy="318" r="142" fill="none" stroke-width="{28+digest[3]%24}"/><path d="M210 414 Q320 {468+shift} 430 414" fill="none" stroke-width="20"/>',
    }
    motif = (
        f'<path d="M238 305 H402 M238 {305+stripe} H402 M238 {305+stripe*2} H402" '
        f'stroke="{accent}" stroke-width="7" opacity=".62" fill="none"/>'
        if digest[4] % 2 else
        f'<circle cx="{280+shift}" cy="330" r="{18+digest[5]%24}" fill="{accent}" opacity=".7"/>'
        f'<circle cx="{366-shift}" cy="382" r="{12+digest[6]%20}" fill="{accent}" opacity=".55"/>'
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640">
<rect width="640" height="640" rx="36" fill="#f3f0e9"/>
<ellipse cx="320" cy="526" rx="190" ry="25" fill="#d9d3c9" opacity=".55"/>
<g fill="{base}" stroke="#504b45" stroke-width="8" stroke-linejoin="round">{shapes[item.category]}</g>
{motif}
</svg>'''


def assign_unique_demo_image(item: WardrobeItem) -> None:
    PUBLIC_CLOTHES.mkdir(parents=True, exist_ok=True)
    filename = f"wardrobe-{item.id}.svg"
    (PUBLIC_CLOTHES / filename).write_text(_svg_art(item), encoding="utf-8")
    item.image_url = f"/clothes/{filename}"


def build_item(category: str, index: int, template: tuple) -> WardrobeItem:
    name, color, image, styles, seasons = template
    is_outer = category == "外套"
    warmth = 3 if is_outer else 1 if category in {"连衣裙", "配饰"} else 2
    formality = 4 if "商务" in styles else 3 if "通勤" in styles else 2
    status = "可穿" if index % 10 else "待洗" if index % 20 else "季节性收纳"
    return WardrobeItem(
        id=f"demo_{CATEGORY_KEYS[category]}_{index:03d}",
        user_id=settings.demo_user_id,
        category=category,
        subcategory=f"{name} {index:02d}",
        colors=[color],
        material_guess=[],
        material_confidence=0.0,
        pattern="纯色",
        fit="常规",
        length="常规",
        wearing_layer="外搭" if is_outer else "不可叠穿" if category == "连衣裙" else "主上装",
        warmth_level=warmth,
        formality_level=formality,
        styles=styles,
        seasons=seasons,
        weather_constraints=["避雨"] if "缎面" in name else [],
        clean_status=status,
        wear_count=index % 9,
        # 新增衣物必须使用真实商品图；未提供真实图时保持为空，不再生成或复用占位图。
        image_url=None,
    )


def main() -> None:
    with SessionLocal() as db:
        rows = list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == settings.demo_user_id)))
        counts = Counter(item.category for item in rows)
        existing_ids = {item.id for item in rows}
        added = Counter()
        for category in CATEGORY_KEYS:
            template_cycle = cycle(TEMPLATES[category])
            index = 1
            while counts[category] < TARGET:
                template = next(template_cycle)
                item_id = f"demo_{CATEGORY_KEYS[category]}_{index:03d}"
                index += 1
                if item_id in existing_ids:
                    continue
                db.add(build_item(category, index - 1, template))
                existing_ids.add(item_id)
                counts[category] += 1
                added[category] += 1
        db.commit()
        print({"added": dict(added), "final": {category: counts[category] for category in CATEGORY_KEYS}, "total": sum(counts[category] for category in CATEGORY_KEYS)})


if __name__ == "__main__":
    main()
