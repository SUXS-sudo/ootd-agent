import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.photo_analysis import analyze_outfit_image


async def main() -> None:
    project = Path(__file__).resolve().parents[2]
    image = project / "tests" / "fixtures" / "people" / "男人.jpg"
    wardrobe = [
        SimpleNamespace(
            id="test_top",
            category="上装",
            subcategory="白色衬衫",
            colors=["白色"],
            styles=["通勤"],
            clean_status="可穿",
        )
    ]
    result = await analyze_outfit_image(image, wardrobe, "日常通勤", "24℃，多云")
    print({
        "status": "ok",
        "guard": result.evidence_guard,
        "observation_count": len(result.observations),
        "tip_count": len(result.actionable_tips),
        "strongest_issue": result.strongest_issue,
    })


if __name__ == "__main__":
    asyncio.run(main())
