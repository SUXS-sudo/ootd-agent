"""core V1 tables
Revision ID: 0001_core
"""
from alembic import op
import sqlalchemy as sa
revision="0001_core";down_revision=None;branch_labels=None;depends_on=None
def upgrade():
    op.create_table("users",sa.Column("id",sa.String(),primary_key=True),sa.Column("email",sa.String(),unique=True),sa.Column("created_at",sa.DateTime()))
    op.create_table("user_profiles",sa.Column("user_id",sa.String(),sa.ForeignKey("users.id"),primary_key=True),sa.Column("height_cm",sa.Integer()),sa.Column("temperature_preference",sa.String(),nullable=False),sa.Column("preferred_styles",sa.JSON()),sa.Column("preferred_colors",sa.JSON()),sa.Column("avoided_colors",sa.JSON()),sa.Column("restrictions",sa.JSON()),sa.Column("visual_goals",sa.JSON()),sa.Column("photo_retention_consent",sa.Boolean(),nullable=False))
    op.create_table("wardrobe_items",sa.Column("id",sa.String(),primary_key=True),sa.Column("user_id",sa.String(),sa.ForeignKey("users.id"),index=True),sa.Column("category",sa.String()),sa.Column("subcategory",sa.String()),sa.Column("colors",sa.JSON()),sa.Column("material_guess",sa.JSON()),sa.Column("material_confidence",sa.Float()),sa.Column("pattern",sa.String()),sa.Column("fit",sa.String()),sa.Column("length",sa.String()),sa.Column("warmth_level",sa.Integer()),sa.Column("formality_level",sa.Integer()),sa.Column("styles",sa.JSON()),sa.Column("seasons",sa.JSON()),sa.Column("weather_constraints",sa.JSON()),sa.Column("clean_status",sa.String()),sa.Column("wear_count",sa.Integer()),sa.Column("last_worn_at",sa.DateTime()),sa.Column("image_url",sa.String()),sa.Column("created_at",sa.DateTime()))
def downgrade():
    op.drop_table("wardrobe_items");op.drop_table("user_profiles");op.drop_table("users")
