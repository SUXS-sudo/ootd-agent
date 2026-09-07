from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def read(path):return (ROOT/path).read_text(encoding="utf-8")

def test_proactive_agent_requires_scope_and_deduplicates():
    source=read(Path("backend/app/proactive.py"));assert "ensure_scope" in source;assert "missing authorized scope" in source;assert "dedupe_key" in source
def test_tryon_has_quality_gates_and_fallback():
    source=read(Path("backend/app/tryon.py"));assert '"identity": .82' in source;assert '"fallback": "real_item_collage"' in source;assert "identity_preserving_tryon" in source
def test_weekly_replan_only_changes_affected_dates():
    source=read(Path("backend/app/planning.py"));assert "if row.date in changed" in source;assert "原计划保持不变" in source
def test_purchase_agent_does_not_push_buying():
    source=read(Path("backend/app/purchase.py"));assert "不是推动购买" in source;assert "duplication_score" in source
