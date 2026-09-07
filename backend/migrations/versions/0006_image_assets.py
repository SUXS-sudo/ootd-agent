"""Store wardrobe images as private object-storage assets.

Revision ID: 0006_image_assets
Revises: 0005_preference_onboarding
"""
from alembic import op
import sqlalchemy as sa

revision="0006_image_assets";down_revision="0005_preference_onboarding";branch_labels=None;depends_on=None

def upgrade():
    op.create_table(
        "image_assets",
        sa.Column("id",sa.String(255),primary_key=True),
        sa.Column("user_id",sa.String(255),sa.ForeignKey("users.id"),nullable=False,index=True),
        sa.Column("kind",sa.String(255),nullable=False,index=True),
        sa.Column("storage_backend",sa.String(255),nullable=False),
        sa.Column("bucket",sa.String(255)),
        sa.Column("object_key",sa.String(255),nullable=False,unique=True),
        sa.Column("original_filename",sa.String(255),nullable=False),
        sa.Column("content_type",sa.String(255),nullable=False),
        sa.Column("byte_size",sa.Integer(),nullable=False),
        sa.Column("sha256",sa.String(255)),
        sa.Column("width",sa.Integer()),sa.Column("height",sa.Integer()),
        sa.Column("variants",sa.JSON(),nullable=False),
        sa.Column("status",sa.String(255),nullable=False,index=True),
        sa.Column("deleted_at",sa.DateTime()),sa.Column("created_at",sa.DateTime(),nullable=False),
    )
    op.add_column("wardrobe_items",sa.Column("image_asset_id",sa.String(255),sa.ForeignKey("image_assets.id"),nullable=True,index=True))

def downgrade():
    op.drop_column("wardrobe_items","image_asset_id");op.drop_table("image_assets")
