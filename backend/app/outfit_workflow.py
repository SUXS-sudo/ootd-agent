from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent import rank_with_model
from .answer_guard import guard_outfit_answer
from .config import settings
from .intent import candidate_satisfies_handoff, merge_conversation_context, prefilter_items_by_handoff, understand_outfit_request
from .models import BanditState, StylingSession, WardrobeItem
from .decisioning import annotate_control_propensity,latest_model,learned_rank_candidates,policy_assignment,thompson_rank_candidates
from .personalization import context_key, feedback_affinities
from .preference_cache import context_preferences, recommendation_profile
from .ranking import COLOR_FAMILIES, deterministic_results, filter_items, generate_candidates, personalize_candidates, required_full_look_color, required_item_terms, resolve_request_context
from .schemas import OutfitRequest, OutfitResult


class OutfitWorkflowError(Exception):
    def __init__(self, detail: dict[str, Any]):
        super().__init__(detail.get("message", "穿搭工作流执行失败"))
        self.detail = detail


@dataclass
class OutfitRuntimeContext:
    db: Session
    user_id: str


class OutfitAgentState(TypedDict, total=False):
    request: dict[str, Any]
    handoff: dict[str, Any]
    candidates: list[dict[str, Any]]
    fallback: list[dict[str, Any]]
    results: list[dict[str, Any]]
    source: str
    guard: dict[str, Any]
    image_tasks: list[dict[str, Any]]
    thread_id: str
    ranking_model_version: str
    policy_version: str


def _request(state: OutfitAgentState) -> OutfitRequest:
    return OutfitRequest.model_validate(state["request"])


def _items(runtime: Runtime[OutfitRuntimeContext]) -> list[WardrobeItem]:
    context = runtime.context
    return list(context.db.scalars(select(WardrobeItem).where(WardrobeItem.user_id == context.user_id)))


def _serialize_candidates(candidates: list[Any]) -> list[dict[str, Any]]:
    return [{"total": total, "item_ids": [item.id for item in items], "scores": scores} for total, items, scores in candidates]


def _hydrate_candidates(serialized: list[dict[str, Any]], items: list[WardrobeItem]) -> list[Any]:
    by_id = {item.id: item for item in items}
    return [(row["total"], [by_id[item_id] for item_id in row["item_ids"] if item_id in by_id], row["scores"]) for row in serialized]


def load_context(state: OutfitAgentState, runtime: Runtime[OutfitRuntimeContext]) -> dict[str, Any]:
    request = resolve_request_context(_request(state))
    return {"request": request.model_dump(mode="json")}


def understand_request(state: OutfitAgentState, runtime: Runtime[OutfitRuntimeContext]) -> dict[str, Any]:
    context, request, items = runtime.context, _request(state), _items(runtime)
    profile = recommendation_profile(context.db, context.user_id)
    session = context.db.get(StylingSession, request.session_id) if request.session_id else None
    if session and session.user_id != context.user_id:
        session = None
    history = session.turns if session else request.chat_history
    interpreted = request.model_copy(update={"chat_history": history[-8:]})
    handoff = understand_outfit_request(interpreted, items, allow_model=request.mode == "deep", profile=profile)
    query = " ".join(value for value in [request.occasion, *request.temporary_requirements] if value)
    handoff = merge_conversation_context(handoff, session.last_handoff if session else None, session.last_outfits if session else [], query, items)
    if handoff.get("needs_clarification"):
        raise OutfitWorkflowError({
            "code": "CLARIFICATION_REQUIRED",
            "message": handoff.get("clarification", {}).get("question") or "我还不能可靠确定你的穿搭要求，请补充要保留、排除或调整的具体内容。",
            "intent_understanding": handoff,
        })
    return {"handoff": handoff}


def build_candidates(state: OutfitAgentState, runtime: Runtime[OutfitRuntimeContext]) -> dict[str, Any]:
    context, request, handoff = runtime.context, _request(state), state["handoff"]
    items = _items(runtime)
    profile = recommendation_profile(context.db, context.user_id)
    valid = prefilter_items_by_handoff(filter_items(items, request, profile), handoff)
    preferences = context_preferences(context.db, context.user_id, context_key(request.occasion))
    candidates = generate_candidates(valid, request, preferences["weights"] if preferences else None, profile)
    candidates = personalize_candidates(candidates,feedback_affinities(context.db,context.user_id,context_key(request.occasion)))
    candidates = [candidate for candidate in candidates if candidate_satisfies_handoff(candidate[1], handoff)]
    model=latest_model(context.db);candidates=learned_rank_candidates(candidates,model)
    ctx=context_key(request.occasion);assignment=policy_assignment(context.db,context.user_id);bandit=context.db.scalar(select(BanditState).where(BanditState.user_id==context.user_id,BanditState.context_key==ctx))
    if assignment.variant=="thompson_sampling":candidates=thompson_rank_candidates(candidates,bandit)
    else:candidates=annotate_control_propensity(candidates)
    if len(candidates) < 3:
        color_requirement = required_full_look_color(request)
        if color_requirement:
            color, _ = color_requirement
            available_categories = {item.category for item in valid if any(any(token in value for token in COLOR_FAMILIES[color]) for value in item.colors)}
            missing = [name for category, name in (("上装", "上装"), ("下装", "下装")) if category not in available_categories]
            raise OutfitWorkflowError({"code": "FULL_LOOK_COLOR_UNAVAILABLE", "message": f"我理解你要一身{color}，但当前可穿衣橱缺少{color}{'、'.join(missing) or '足够的可组合单品'}，无法组成完整同色套装；我不会用其他颜色替代。"})
        if handoff.get("hard_constraints"):
            constraints = "、".join(str(value["source_span"]) for value in handoff["hard_constraints"])
            raise OutfitWorkflowError({"code": "INTENT_CONSTRAINTS_UNAVAILABLE", "message": f"我理解你的明确要求是：{constraints}。当前可穿衣橱无法组成三套满足全部要求的搭配，我不会用不符合条件的方案凑数。", "intent_understanding": handoff})
        requested = required_item_terms(request)
        raise OutfitWorkflowError({"code": "REQUIRED_ITEM_UNAVAILABLE" if requested else "NOT_ENOUGH_VALID_COMBINATIONS", "message": "衣橱中没有足够的可穿单品满足你明确指定的衣物要求" if requested else "可穿衣物不足以生成三套不重复方案"})
    fallback = deterministic_results(candidates, request)
    return {"candidates": _serialize_candidates(candidates), "fallback": [result.model_dump(mode="json") for result in fallback],"ranking_model_version":model.version if model else "rules-v1","policy_version":assignment.variant}


def decide(state: OutfitAgentState, runtime: Runtime[OutfitRuntimeContext]) -> dict[str, Any]:
    request = _request(state)
    if request.mode == "fast":
        return {"results": state["fallback"], "source": "rules_fast"}
    candidates = _hydrate_candidates(state["candidates"], _items(runtime))
    fallback = [OutfitResult.model_validate(result) for result in state["fallback"]]
    results, source = rank_with_model(runtime.context.db, runtime.context.user_id, candidates, request, fallback, state["handoff"])
    return {"results": [result.model_dump(mode="json") for result in results], "source": source}


def validate(state: OutfitAgentState, runtime: Runtime[OutfitRuntimeContext]) -> dict[str, Any]:
    items = _items(runtime)
    guard = guard_outfit_answer(
        [OutfitResult.model_validate(result) for result in state["results"]],
        _hydrate_candidates(state["candidates"], items),
        state["handoff"],
        {item.id: item for item in items},
    )
    return {"guard": guard}


def validation_route(state: OutfitAgentState) -> Literal["complete", "fallback"]:
    return "complete" if state["guard"]["status"] == "passed" else "fallback"


def apply_fallback(state: OutfitAgentState, runtime: Runtime[OutfitRuntimeContext]) -> dict[str, Any]:
    items = _items(runtime)
    fallback = [OutfitResult.model_validate(result) for result in state["fallback"]]
    guard = guard_outfit_answer(fallback, _hydrate_candidates(state["candidates"], items), state["handoff"], {item.id: item for item in items})
    guard.update({"retry_count": 1, "fallback_used": True})
    return {"results": state["fallback"], "source": "guarded_rules", "guard": guard}


def prepare_image_generation(state: OutfitAgentState, runtime: Runtime[OutfitRuntimeContext]) -> dict[str, Any]:
    items_by_id = {item.id: item for item in _items(runtime)}
    tasks = []
    for result in state["results"]:
        item_ids = result["item_ids"]
        tasks.append({
            "task_id": f"img_{uuid.uuid4().hex[:10]}",
            "kind": "collage",
            "item_ids": item_ids,
            "item_images": [items_by_id[item_id].image_url for item_id in item_ids if item_id in items_by_id and items_by_id[item_id].image_url],
        })
    return {"image_tasks": tasks}


_checkpoint_context = PyMySQLSaver.from_conn_string(settings.langgraph_checkpoint_url)
outfit_checkpointer = _checkpoint_context.__enter__()
outfit_checkpointer.setup()


def _build_graph():
    graph = StateGraph(OutfitAgentState, context_schema=OutfitRuntimeContext)
    graph.add_node("load_context", load_context)
    graph.add_node("understand_request", understand_request)
    graph.add_node("build_candidates", build_candidates)
    graph.add_node("decide", decide)
    graph.add_node("validate", validate)
    graph.add_node("fallback", apply_fallback)
    graph.add_node("prepare_image_generation", prepare_image_generation)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "understand_request")
    graph.add_edge("understand_request", "build_candidates")
    graph.add_edge("build_candidates", "decide")
    graph.add_edge("decide", "validate")
    graph.add_conditional_edges("validate", validation_route, {"complete": "prepare_image_generation", "fallback": "fallback"})
    graph.add_edge("fallback", "prepare_image_generation")
    graph.add_edge("prepare_image_generation", END)
    return graph.compile(checkpointer=outfit_checkpointer)


outfit_agent_graph = _build_graph()


def run_outfit_agent(db: Session, user_id: str, request: OutfitRequest) -> OutfitAgentState:
    thread_id = request.session_id or f"outfit:{user_id}:{uuid.uuid4().hex}"
    state = outfit_agent_graph.invoke(
        {"request": request.model_dump(mode="json"), "thread_id": thread_id},
        config={"configurable": {"thread_id": thread_id}},
        context=OutfitRuntimeContext(db=db, user_id=user_id),
    )
    state["request"] = OutfitRequest.model_validate(state["request"])
    state["results"] = [OutfitResult.model_validate(result) for result in state["results"]]
    return state
