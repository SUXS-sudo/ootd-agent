"""Distinguish real user feedback from expert-proxy labels."""
from alembic import op
import sqlalchemy as sa

revision="0008_outcome_source";down_revision="0007_learning_decisions";branch_labels=None;depends_on=None

def upgrade():op.add_column("decision_outcomes",sa.Column("source",sa.String(255),nullable=False,server_default="user_feedback"));op.create_index("ix_decision_outcomes_source","decision_outcomes",["source"])
def downgrade():op.drop_index("ix_decision_outcomes_source",table_name="decision_outcomes");op.drop_column("decision_outcomes","source")
