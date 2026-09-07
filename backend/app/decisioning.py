from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .models import (
    BanditState,
    CandidateImpression,
    DecisionOutcome,
    PolicyAssignment,
    PreferenceDriftEvent,
    RankingModel,
    RecommendationDecision,
)

FEATURE_SCHEMA_VERSION = "features-v3"
FEATURE_NAMES = (
    "weather",
    "occasion",
    "preference",
    "color",
    "proportion",
    "utilization",
    "freshness",
    "personalization",
    "repeat_penalty",
    "bias",
)
POLICY_EXPERIMENT = "ranking-policy-v4"


def sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def policy_assignment(db, user_id: str) -> PolicyAssignment:
    existing = db.scalar(
        select(PolicyAssignment).where(
            PolicyAssignment.user_id == user_id,
            PolicyAssignment.experiment_key == POLICY_EXPERIMENT,
        )
    )
    if existing:
        return existing
    bucket = int(
        hashlib.sha256(f"{POLICY_EXPERIMENT}:{user_id}".encode()).hexdigest()[:8], 16
    ) % 100
    variant = "thompson_sampling" if bucket < 50 else "pairwise_control"
    row = PolicyAssignment(
        id=f"pa_{hashlib.sha1(f'{POLICY_EXPERIMENT}:{user_id}'.encode()).hexdigest()[:16]}",
        user_id=user_id,
        experiment_key=POLICY_EXPERIMENT,
        variant=variant,
    )
    db.add(row)
    db.flush()
    return row


def candidate_features(items, scores: dict) -> dict[str, float]:
    return {
        "weather": float(scores.get("weather", 0.0)),
        "occasion": float(scores.get("occasion", 0.0)),
        "preference": float(scores.get("preference", 0.0)),
        "color": float(scores.get("color", 0.0)),
        "proportion": float(scores.get("proportion", 0.0)),
        "utilization": float(scores.get("utilization", 0.0)),
        "freshness": float(scores.get("freshness", 0.0)),
        "personalization": float(scores.get("personalization", 0.0)),
        "repeat_penalty": float(scores.get("repeat_penalty", 0.0)),
        "bias": 1.0,
    }


def vector(features: dict) -> list[float]:
    return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]


def utility(features: dict, weights: dict) -> float:
    return sum(float(weights.get(name, 0.0)) * float(features.get(name, 0.0)) for name in FEATURE_NAMES)


def train_pairwise(
    samples: list[tuple[dict, dict, float]],
    epochs: int = 260,
    learning_rate: float = 0.07,
    l2: float = 0.01,
) -> dict[str, float]:
    """Fit a linear Bradley-Terry ranker from preferred/non-preferred pairs."""
    weights = {name: 0.0 for name in FEATURE_NAMES}
    if not samples:
        return weights
    for epoch in range(epochs):
        rate = learning_rate / math.sqrt(1.0 + epoch / 40.0)
        for preferred, other, sample_weight in samples:
            delta = {
                name: float(preferred.get(name, 0.0)) - float(other.get(name, 0.0))
                for name in FEATURE_NAMES
            }
            probability = sigmoid(utility(delta, weights))
            error = (1.0 - probability) * float(sample_weight)
            for name in FEATURE_NAMES:
                weights[name] += rate * (error * delta[name] - l2 * weights[name])
    return weights


def pairwise_probability(preferred: dict, other: dict, weights: dict) -> float:
    delta = {
        name: float(preferred.get(name, 0.0)) - float(other.get(name, 0.0))
        for name in FEATURE_NAMES
    }
    return sigmoid(utility(delta, weights))


def model_probability(features: dict, model_or_weights) -> float:
    weights = (model_or_weights.parameters or {}).get("weights", {}) if hasattr(model_or_weights, "parameters") else model_or_weights
    return sigmoid(utility(features, weights))


def latest_model(db) -> RankingModel | None:
    return db.scalar(
        select(RankingModel)
        .where(RankingModel.status == "active")
        .order_by(RankingModel.created_at.desc())
    )


def learned_rank_candidates(candidates, model: RankingModel | None):
    if not model:
        return candidates
    weights = (model.parameters or {}).get("weights", {})
    raw_utilities = [utility(candidate_features(items, scores), weights) for _, items, scores in candidates]
    if raw_utilities:
        center = sum(raw_utilities) / len(raw_utilities)
    else:
        center = 0.0
    ranked = []
    for (base, items, scores), raw_utility in zip(candidates, raw_utilities):
        preference_probability = sigmoid(raw_utility - center)
        final = 0.45 * base + 0.55 * preference_probability
        ranked.append(
            (
                final,
                items,
                {
                    **scores,
                    "pairwise_probability": round(preference_probability, 4),
                    "learned_probability": round(preference_probability, 4),
                    "base_total": round(scores.get("base_total", base), 4),
                },
            )
        )
    return sorted(ranked, key=lambda row: row[0], reverse=True)


def _posterior(state: BanditState | None):
    parameters = state.parameters if state else {}
    legacy_precision = parameters.get("a_diag", {})
    precision = parameters.get("precision_diag", legacy_precision)
    reward_sum = parameters.get("reward_sum", parameters.get("b", {}))
    posterior_mean = parameters.get("posterior_mean", {})
    precision = {name: max(1e-6, float(precision.get(name, 1.0))) for name in FEATURE_NAMES}
    reward_sum = {name: float(reward_sum.get(name, 0.0)) for name in FEATURE_NAMES}
    if not posterior_mean:
        posterior_mean = {name: reward_sum[name] / precision[name] for name in FEATURE_NAMES}
    else:
        posterior_mean = {name: float(posterior_mean.get(name, 0.0)) for name in FEATURE_NAMES}
    return precision, reward_sum, posterior_mean


def _sample_weights(posterior_mean, precision, rng: random.Random):
    return {
        name: rng.gauss(posterior_mean[name], 1.0 / math.sqrt(precision[name]))
        for name in FEATURE_NAMES
    }


def thompson_rank_candidates(
    candidates,
    state: BanditState | None,
    exploration_rate: float = 0.05,
    max_regret: float = 0.10,
    posterior_draws: int = 128,
    rng: random.Random | None = None,
):
    """Explore only among candidates inside the base-score quality gate."""
    if not candidates:
        return candidates
    rng = rng or random.Random()
    precision, _, posterior_mean = _posterior(state)
    best_base = max(float(row[2].get("base_total", row[0])) for row in candidates)
    eligible = [
        index
        for index, row in enumerate(candidates)
        if float(row[2].get("base_total", row[0])) >= best_base - max_regret
    ]
    feature_rows = [candidate_features(items, scores) for _, items, scores in candidates]
    wins = [0 for _ in candidates]
    for _ in range(max(1, posterior_draws)):
        sampled = _sample_weights(posterior_mean, precision, rng)
        winner = max(eligible, key=lambda index: utility(feature_rows[index], sampled))
        wins[winner] += 1
    exploit_winner = max(eligible, key=lambda index: utility(feature_rows[index], posterior_mean))
    explore = len(eligible) > 1 and rng.random() < exploration_rate
    selected = exploit_winner
    if explore:
        sampled = _sample_weights(posterior_mean, precision, rng)
        selected = max(eligible, key=lambda index: utility(feature_rows[index], sampled))
    result = []
    top_final_score = max(float(row[0]) for row in candidates)
    for index, (score, items, scores) in enumerate(candidates):
        uncertainty = math.sqrt(
            sum((feature_rows[index][name] ** 2) / precision[name] for name in FEATURE_NAMES)
        )
        selection_probability = (1.0 - exploration_rate) * float(index == exploit_winner)
        selection_probability += exploration_rate * wins[index] / max(1, posterior_draws)
        final_score = top_final_score + 1e-6 if index == selected else score
        result.append(
            (
                final_score,
                items,
                {
                    **scores,
                    "bandit_uncertainty": round(uncertainty, 4),
                    "selection_probability": round(selection_probability, 6),
                    "exploration_eligible": index in eligible,
                    "exploration_applied": explore,
                },
            )
        )
    return sorted(result, key=lambda row: row[0], reverse=True)


def annotate_control_propensity(candidates):
    return [
        (
            score,
            items,
            {
                **scores,
                "selection_probability": 1.0 if index == 0 else 0.0,
                "exploration_eligible": False,
                "exploration_applied": False,
            },
        )
        for index, (score, items, scores) in enumerate(candidates)
    ]


def update_thompson(db, user_id: str, context: str, features: dict, reward: float):
    state = db.scalar(
        select(BanditState).where(BanditState.user_id == user_id, BanditState.context_key == context)
    )
    if not state:
        state = BanditState(
            id=f"bandit_{hashlib.sha1(f'{user_id}:{context}'.encode()).hexdigest()[:16]}",
            user_id=user_id,
            context_key=context,
            policy_version="thompson-v1",
            parameters={},
        )
        db.add(state)
    precision, reward_sum, _ = _posterior(state)
    for name in FEATURE_NAMES:
        value = float(features.get(name, 0.0))
        precision[name] += value * value
        reward_sum[name] += reward * value
    posterior_mean = {name: reward_sum[name] / precision[name] for name in FEATURE_NAMES}
    state.parameters = {
        "precision_diag": precision,
        "reward_sum": reward_sum,
        "posterior_mean": posterior_mean,
    }
    state.sample_count = int(state.sample_count or 0) + 1
    db.flush()
    return state


def outcome_reward(adopted: bool, replaced_item_ids=None, tags=None, source: str = "direct") -> float:
    reward = 1.0 if adopted else -0.7
    if adopted and (source == "replacement" or bool(replaced_item_ids)):
        reward = 0.65
    tag_set = set(tags or [])
    if "dont_recommend_again" in tag_set:
        reward -= 0.6
    if "temperature_mismatch" in tag_set:
        reward -= 0.2
    if "comfort" in tag_set and adopted:
        reward += 0.1
    return max(-1.0, min(1.0, reward))


def _pairwise_metrics(samples, weights):
    if not samples:
        return {"pairwise_accuracy": 0.0, "pairwise_log_loss": 0.0, "pair_count": 0}
    probabilities = [pairwise_probability(preferred, other, weights) for preferred, other, _ in samples]
    accuracy = sum(probability >= 0.5 for probability in probabilities) / len(probabilities)
    log_loss = -sum(math.log(max(1e-8, probability)) for probability in probabilities) / len(probabilities)
    return {
        "pairwise_accuracy": round(accuracy, 4),
        "pairwise_log_loss": round(log_loss, 4),
        "pair_count": len(samples),
    }


def ranking_metrics(rows, weights):
    groups = defaultdict(list)
    for decision_id, features, label in rows:
        groups[decision_id].append((utility(features, weights), label))
    ndcgs = []
    for group in groups.values():
        ranked = sorted(group, reverse=True)[:3]
        dcg = sum(label / math.log2(index + 2) for index, (_, label) in enumerate(ranked))
        ideal = sorted((label for _, label in group), reverse=True)[:3]
        idcg = sum(label / math.log2(index + 2) for index, label in enumerate(ideal))
        if idcg > 0:
            ndcgs.append(dcg / idcg)
    return {"ndcg_at_3": round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else 0.0}


def _pair_samples(decision_rows, outcomes, sources):
    samples = []
    ranking_rows = []
    for decision_id, rows in decision_rows.items():
        outcomes_by_impression = {outcome.impression_id: outcome for outcome in outcomes.get(decision_id, [])}
        positives = []
        negatives = []
        neutral = []
        for row in rows:
            if not row.displayed:
                continue
            outcome = outcomes_by_impression.get(row.id)
            label = 1.0 if outcome and outcome.adopted else 0.0
            ranking_rows.append((decision_id, row.feature_snapshot, label))
            if outcome and outcome.adopted:
                positives.append(row)
            elif outcome:
                negatives.append(row)
            else:
                neutral.append(row)
        source_weight = 0.35 if sources.get(decision_id) == "expert_proxy" else 1.0
        for positive in positives:
            for other in negatives + neutral:
                samples.append((positive.feature_snapshot, other.feature_snapshot, source_weight))
        if not positives:
            for rejected in negatives:
                for other in neutral:
                    samples.append((other.feature_snapshot, rejected.feature_snapshot, source_weight * 0.6))
    return samples, ranking_rows


def train_and_evaluate(db, days: int = 120):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    decisions = list(
        db.scalars(
            select(RecommendationDecision)
            .where(RecommendationDecision.created_at >= cutoff)
            .order_by(RecommendationDecision.created_at)
        )
    )
    if len(decisions) < 3:
        return None
    decision_ids = [row.id for row in decisions]
    impressions = list(
        db.scalars(select(CandidateImpression).where(CandidateImpression.decision_id.in_(decision_ids)))
    )
    outcomes = list(db.scalars(select(DecisionOutcome).where(DecisionOutcome.decision_id.in_(decision_ids))))
    impressions_by_decision = defaultdict(list)
    outcomes_by_decision = defaultdict(list)
    for row in impressions:
        impressions_by_decision[row.decision_id].append(row)
    for row in outcomes:
        outcomes_by_decision[row.decision_id].append(row)
    sources = {
        row.id: ("expert_proxy" if any(outcome.source == "expert_proxy" for outcome in outcomes_by_decision[row.id]) else "real_user")
        for row in decisions
    }
    split = max(1, int(len(decisions) * 0.7))
    train_ids = {row.id for row in decisions[:split]}
    test_ids = {row.id for row in decisions[split:]}
    train_pairs, _ = _pair_samples(
        {key: value for key, value in impressions_by_decision.items() if key in train_ids},
        outcomes_by_decision,
        sources,
    )
    test_pairs, test_rows = _pair_samples(
        {key: value for key, value in impressions_by_decision.items() if key in test_ids},
        outcomes_by_decision,
        sources,
    )
    if not train_pairs or not test_pairs:
        return None
    weights = train_pairwise(train_pairs)
    metrics = {**_pairwise_metrics(test_pairs, weights), **ranking_metrics(test_rows, weights)}
    current = latest_model(db)
    if current:
        current.status = "archived"
    version = f"pairwise-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    model = RankingModel(
        id=f"model_{hashlib.sha1(version.encode()).hexdigest()[:16]}",
        version=version,
        model_type="linear_pairwise_logistic",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        parameters={"weights": weights},
        calibration={},
        metrics=metrics,
        training_window={
            "from": cutoff.isoformat(),
            "to": datetime.now(timezone.utc).isoformat(),
            "train_decisions": len(train_ids),
            "test_decisions": len(test_ids),
            "proxy_weight": 0.35,
        },
        status="active",
    )
    db.add(model)
    db.flush()
    return model


def detect_preference_drift(db, user_id: str, context: str, window: int = 30, threshold: float = 0.18):
    rows = list(
        db.scalars(
            select(DecisionOutcome)
            .join(
                RecommendationDecision,
                DecisionOutcome.decision_id == RecommendationDecision.id,
            )
            .where(
                RecommendationDecision.user_id == user_id,
                RecommendationDecision.context_key == context,
            )
            .order_by(DecisionOutcome.created_at.desc())
            .limit(window * 2)
        )
    )
    if len(rows) < 20:
        return None
    recent, baseline = rows[:window], rows[window : window * 2]
    recent_rate = sum(bool(row.adopted) for row in recent) / len(recent)
    baseline_rate = sum(bool(row.adopted) for row in baseline) / len(baseline)
    score = abs(recent_rate - baseline_rate)
    if score < threshold:
        return None
    event = PreferenceDriftEvent(
        id=f"drift_{hashlib.sha1(f'{user_id}:{context}:{datetime.now(timezone.utc).isoformat()}'.encode()).hexdigest()[:16]}",
        user_id=user_id,
        context_key=context,
        feature_key="acceptance_rate",
        long_term_value=baseline_rate,
        recent_value=recent_rate,
        magnitude=score,
    )
    db.add(event)
    db.flush()
    return event


def counterfactual(features: dict, model: RankingModel | None, changes: dict):
    if not model:
        return {"base_probability": 0.5, "new_probability": 0.5, "delta": 0.0, "factors": [], "consistent": True}
    weights = (model.parameters or {}).get("weights", {})
    changed = {**features, **changes}
    base_probability = model_probability(features, weights)
    new_probability = model_probability(changed, weights)
    factors = sorted(
        (
            {
                "feature": name,
                "change": round(float(changed.get(name, 0.0)) - float(features.get(name, 0.0)), 4),
                "contribution": round((float(changed.get(name, 0.0)) - float(features.get(name, 0.0))) * float(weights.get(name, 0.0)), 4),
            }
            for name in changes
        ),
        key=lambda row: abs(row["contribution"]),
        reverse=True,
    )
    contribution_sum = sum(row["contribution"] for row in factors)
    delta = new_probability - base_probability
    return {
        "base_probability": round(base_probability, 4),
        "new_probability": round(new_probability, 4),
        "delta": round(delta, 4),
        "factors": factors,
        "consistent": delta == 0 or contribution_sum == 0 or (delta > 0) == (contribution_sum > 0),
    }
