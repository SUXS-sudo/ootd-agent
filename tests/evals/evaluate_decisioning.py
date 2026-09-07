"""Reproducible synthetic gates for pairwise ranking and quality-gated exploration."""
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace as S

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.decisioning import FEATURE_NAMES, pairwise_probability, thompson_rank_candidates, train_pairwise


def features(weather, preference):
    row = {name: 0.5 for name in FEATURE_NAMES}
    row.update({"weather": weather, "preference": preference, "bias": 1.0})
    return row


def main():
    positive = features(0.9, 0.8)
    negative = features(0.2, 0.3)
    weights = train_pairwise([(positive, negative, 1.0)] * 24)
    probability = pairwise_probability(positive, negative, weights)

    item = lambda item_id: S(id=item_id, wear_count=0)
    candidates = [
        (0.9, [item("best")], {"weather": 0.9, "base_total": 0.9}),
        (0.86, [item("eligible")], {"weather": 0.8, "base_total": 0.86}),
        (0.5, [item("unsafe")], {"weather": 0.2, "base_total": 0.5}),
    ]
    unsafe_promoted = False
    for seed in range(200):
        ranked = thompson_rank_candidates(
            candidates,
            None,
            exploration_rate=1.0,
            max_regret=0.1,
            posterior_draws=64,
            rng=random.Random(seed),
        )
        unsafe_promoted |= ranked[0][1][0].id == "unsafe"

    assert probability >= 0.8
    assert unsafe_promoted is False
    print(
        json.dumps(
            {
                "ranker": {"type": "linear_pairwise_logistic", "preferred_pair_probability": round(probability, 4)},
                "exploration": {"type": "thompson_sampling", "quality_gate": 0.1, "unsafe_candidate_promoted": unsafe_promoted},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
