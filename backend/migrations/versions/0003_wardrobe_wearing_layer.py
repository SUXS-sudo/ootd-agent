"""add wardrobe wearing layer

Revision ID: 0003_wardrobe_wearing_layer
Revises: 0002_personal_agent
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_wardrobe_wearing_layer"
down_revision = "0002_personal_agent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("wardrobe_items", sa.Column("wearing_layer", sa.String(), nullable=False, server_default="主上装"))
    op.execute("UPDATE wardrobe_items SET wearing_layer = '外搭' WHERE category = '外套'")


def downgrade():
    op.drop_column("wardrobe_items", "wearing_layer")
