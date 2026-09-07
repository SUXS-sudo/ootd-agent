"""Local password authentication and refresh sessions.

Revision ID: 0004_local_auth
"""
from alembic import op
import sqlalchemy as sa

revision="0004_local_auth";down_revision="0003_wardrobe_wearing_layer";branch_labels=None;depends_on=None

def upgrade():
    op.add_column("users",sa.Column("password_hash",sa.String(),nullable=True))
    op.add_column("users",sa.Column("password_salt",sa.String(),nullable=True))
    op.create_table("auth_sessions",sa.Column("id",sa.String(),primary_key=True),sa.Column("user_id",sa.String(),sa.ForeignKey("users.id"),index=True),sa.Column("expires_at",sa.DateTime(),index=True),sa.Column("revoked_at",sa.DateTime(),nullable=True),sa.Column("created_at",sa.DateTime()))

def downgrade():
    op.drop_table("auth_sessions");op.drop_column("users","password_salt");op.drop_column("users","password_hash")
