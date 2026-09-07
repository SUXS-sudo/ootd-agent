"""Sync real catalog images into demo wardrobe rows using the prompt manifest."""

import re
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import WardrobeItem


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / "docs" / "image-generation" / "衣橱真实商品图-生图提示词.md"
IMAGE_DIR = PROJECT_ROOT / "public" / "clothes"
CATEGORY_KEYS = {
    "上装": "top",
    "下装": "bottom",
    "连衣裙": "dress",
    "外套": "outer",
    "鞋履": "shoes",
    "包袋": "bag",
    "配饰": "accessory",
}
ITEM_PATTERN = re.compile(r"^(\d+)\. (.+?) — `(.+?\.(?:png|jpg|jpeg|webp))`$", re.I)


def manifest_items():
    category = None
    for raw_line in MANIFEST.read_text(encoding="utf-8-sig").splitlines():
        if raw_line.startswith("## "):
            heading = raw_line[3:].split()[0]
            category = heading if heading in CATEGORY_KEYS else None
            continue
        match = ITEM_PATTERN.match(raw_line.strip())
        if category and match:
            index, name, filename = match.groups()
            yield category, int(index), name, filename


def main() -> None:
    linked = []
    missing_rows = []
    with SessionLocal() as db:
        for category, index, name, filename in manifest_items():
            image_path = IMAGE_DIR / filename
            if not image_path.is_file():
                continue
            item_id = f"demo_{CATEGORY_KEYS[category]}_{index:03d}"
            row = db.get(WardrobeItem, item_id)
            if not row:
                missing_rows.append(item_id)
                continue
            row.category = category
            row.subcategory = name
            row.image_url = f"/clothes/{filename}"
            linked.append((item_id, filename))
        db.commit()
    print({"linked": len(linked), "missing_rows": missing_rows})
    for item_id, filename in linked:
        print(f"{item_id} -> {filename}")


if __name__ == "__main__":
    main()
