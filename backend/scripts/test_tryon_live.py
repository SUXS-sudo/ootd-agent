import asyncio
from pathlib import Path

from starlette.datastructures import UploadFile

from app.tryon import generate_tryon


async def main() -> None:
    project = Path(__file__).resolve().parents[2]
    person_path = project / "tests" / "fixtures" / "people" / "男人.jpg"
    garment_path = project / "tests" / "fixtures" / "people" / "男生夏季穿搭，清爽不单调的搭配技巧_1_KK教穿搭_来自小红书网页版.jpg"
    with person_path.open("rb") as person_file, garment_path.open("rb") as garment_file:
        result = await generate_tryon(
            UploadFile(person_file, filename=person_path.name),
            UploadFile(garment_file, filename=garment_path.name),
            "第一张是人物原图，第二张是九套夏季穿搭参考。保持人物身份、脸、姿势和户外背景不变，"
            "将人物服装替换为参考图左上角第一套：浅灰色宽松短袖、黑色宽腿长裤、黑色低帮运动鞋。"
            "生成写实自然的单张全身照片，不要文字、拼图或水印。",
        )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
