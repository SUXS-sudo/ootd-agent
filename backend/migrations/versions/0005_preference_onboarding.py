"""Add explicit liked and disliked style and garment preferences.

Revision ID: 0005_preference_onboarding
"""
from alembic import op
import sqlalchemy as sa

revision="0005_preference_onboarding";down_revision="0004_local_auth";branch_labels=None;depends_on=None

def upgrade():
    op.add_column("user_profiles",sa.Column("avoided_styles",sa.JSON(),nullable=False,server_default="[]"))
    op.add_column("user_profiles",sa.Column("preferred_item_terms",sa.JSON(),nullable=False,server_default="[]"))
    op.add_column("user_profiles",sa.Column("avoided_item_terms",sa.JSON(),nullable=False,server_default="[]"))

def downgrade():
    op.drop_column("user_profiles","avoided_item_terms");op.drop_column("user_profiles","preferred_item_terms");op.drop_column("user_profiles","avoided_styles")
