from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from .config import settings,should_seed_demo_data
from .database import Base,engine,SessionLocal
from .seed import seed_demo
from .api import router

def ensure_schema_compatibility():
    """Keep databases created by earlier application versions schema-compatible."""
    columns={column["name"] for column in inspect(engine).get_columns("wardrobe_items")}
    if "wearing_layer" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE wardrobe_items ADD COLUMN wearing_layer VARCHAR(255) NOT NULL DEFAULT '主上装'"))
            connection.execute(text("UPDATE wardrobe_items SET wearing_layer = '外搭' WHERE category = '外套'"))
    if "image_asset_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE wardrobe_items ADD COLUMN image_asset_id VARCHAR(255) NULL"))
            connection.execute(text("CREATE INDEX ix_wardrobe_items_image_asset_id ON wardrobe_items (image_asset_id)"))
            connection.execute(text("ALTER TABLE wardrobe_items ADD CONSTRAINT fk_wardrobe_image_asset FOREIGN KEY (image_asset_id) REFERENCES image_assets(id)"))
    unique_constraints=inspect(engine).get_unique_constraints("wardrobe_items")
    if not any(constraint.get("column_names")==["image_asset_id"] for constraint in unique_constraints):
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE wardrobe_items ADD CONSTRAINT uq_wardrobe_items_image_asset_id UNIQUE (image_asset_id)"))
    user_columns={column["name"] for column in inspect(engine).get_columns("users")}
    profile_columns={column["name"] for column in inspect(engine).get_columns("user_profiles")}
    with engine.begin() as connection:
        if "password_hash" not in user_columns:connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "password_salt" not in user_columns:connection.execute(text("ALTER TABLE users ADD COLUMN password_salt VARCHAR(255)"))
        for name in ("avoided_styles","preferred_item_terms","avoided_item_terms"):
            if name not in profile_columns:
                connection.execute(text(f"ALTER TABLE user_profiles ADD COLUMN {name} JSON NULL"))
                connection.execute(text(f"UPDATE user_profiles SET {name} = JSON_ARRAY() WHERE {name} IS NULL"))
                connection.execute(text(f"ALTER TABLE user_profiles MODIFY COLUMN {name} JSON NOT NULL"))

@asynccontextmanager
async def lifespan(app:FastAPI):
    Base.metadata.create_all(engine)
    ensure_schema_compatibility()
    if should_seed_demo_data():
        with SessionLocal() as db: seed_demo(db)
    yield

app=FastAPI(title=settings.app_name,version="1.0.0",lifespan=lifespan,docs_url="/api/docs",openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",")],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.mount("/generated",StaticFiles(directory="generated",check_dir=False),name="generated")
app.include_router(router)
