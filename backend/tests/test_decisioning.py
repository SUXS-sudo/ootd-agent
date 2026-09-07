import random
from types import SimpleNamespace as S

from app.decisioning import (
    FEATURE_NAMES,
    candidate_features,
    counterfactual,
    learned_rank_candidates,
    model_probability,
    outcome_reward,
    pairwise_probability,
    policy_assignment,
    ranking_metrics,
    thompson_rank_candidates,
    train_pairwise,
)


def item(item_id, wear=0):
    return S(id=item_id, wear_count=wear)


def candidate(score, item_id, weather=0.8):
    return (
        score,
        [item(item_id)],
        {
            "weather": weather,
            "occasion": 0.8,
            "preference": 0.7,
            "color": 0.7,
            "proportion": 0.7,
            "utilization": 0.5,
            "freshness": 0.5,
            "personalization": 0.5,
            "base_total": score,
        },
    )


def feature(weather):
    row = {name: 0.0 for name in FEATURE_NAMES}
    row.update({"weather": weather, "bias": 1.0})
    return row


def test_pairwise_ranker_learns_preferred_weather_signal():
    preferred, other = feature(1.0), feature(0.0)
    weights = train_pairwise([(preferred, other, 1.0)] * 30)
    assert weights["weather"] > 0
    assert pairwise_probability(preferred, other, weights) > 0.5
    assert model_probability(preferred, weights) > model_probability(other, weights)


def test_pairwise_ranking_metrics_are_bounded():
    weights = {name: 0.0 for name in FEATURE_NAMES}
    weights["weather"] = 1.0
    metrics = ranking_metrics(
        [("d1", feature(0.9), 1), ("d1", feature(0.2), 0), ("d2", feature(0.8), 0), ("d2", feature(0.7), 1)],
        weights,
    )
    assert 0 <= metrics["ndcg_at_3"] <= 1


def test_thompson_never_promotes_candidate_outside_quality_gate():
    candidates = [candidate(0.9, "best"), candidate(0.86, "eligible"), candidate(0.6, "unsafe")]
    state = S(parameters={"precision_diag": {name: 1.0 for name in FEATURE_NAMES}, "reward_sum": {}, "posterior_mean": {}})
    for seed in range(100):
        ranked = thompson_rank_candidates(
            candidates,
            state,
            exploration_rate=1.0,
            max_regret=0.1,
            posterior_draws=32,
            rng=random.Random(seed),
        )
        assert ranked[0][1][0].id != "unsafe"
        unsafe = next(row for row in ranked if row[1][0].id == "unsafe")
        assert unsafe[2]["exploration_eligible"] is False


def test_thompson_records_a_normalized_top_choice_probability():
    ranked = thompson_rank_candidates(
        [candidate(0.9, "best"), candidate(0.86, "eligible"), candidate(0.6, "unsafe")],
        None,
        exploration_rate=0.05,
        posterior_draws=256,
        rng=random.Random(7),
    )
    assert abs(sum(row[2]["selection_probability"] for row in ranked) - 1.0) < 1e-5


def test_learned_ranker_and_counterfactual_use_same_model():
    weights = {name: 0.0 for name in FEATURE_NAMES}
    weights.update({"weather": 4.0, "bias": -2.0})
    model = S(parameters={"weights": weights}, version="test")
    ranked = learned_rank_candidates([candidate(0.7, "warm", 0.95), candidate(0.7, "cold", 0.1)], model)
    assert ranked[0][1][0].id == "warm"
    features = candidate_features(ranked[0][1], ranked[0][2])
    explanation = counterfactual(features, model, {"weather": 0})
    assert explanation["delta"] < 0 and explanation["consistent"] is True


def test_feedback_rewards_preserve_signal_strength():
    assert outcome_reward(True, [], []) > outcome_reward(True, ["shoe"], []) > outcome_reward(False, [], [])


def test_experiment_assignment_is_stable_for_same_user():
    class FakeDb:
        def __init__(self):
            self.row = None

        def scalar(self, query):
            return self.row

        def add(self, row):
            self.row = row

        def flush(self):
            pass

    db = FakeDb()
    first = policy_assignment(db, "same-user")
    second = policy_assignment(db, "same-user")
    assert first.id == second.id and first.variant in {"thompson_sampling", "pairwise_control"}
