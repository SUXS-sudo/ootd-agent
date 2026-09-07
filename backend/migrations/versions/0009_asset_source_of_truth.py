"""Enforce one wardrobe row per durable image asset.

Revision ID: 0009_asset_source_of_truth
Revises: 0008_outcome_source
"""
from alembic import op

revision="0009_asset_source_of_truth"
down_revision="0008_outcome_source"
branch_labels=None
depends_on=None

def upgrade():
    op.create_unique_constraint("uq_wardrobe_items_image_asset_id","wardrobe_items",["image_asset_id"])

def downgrade():
    op.drop_constraint("uq_wardrobe_items_image_asset_id","wardrobe_items",type_="unique")
