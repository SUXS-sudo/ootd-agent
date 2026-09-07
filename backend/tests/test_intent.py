import json
import sys
from types import SimpleNamespace

from app.config import settings
from app.intent import StylingSemantics, _strict_json_schema, candidate_satisfies_handoff, merge_conversation_context, prefilter_items_by_handoff, understand_outfit_request
from app.schemas import OutfitRequest


def item(id,cat,sub,colors):
    return SimpleNamespace(id=id,category=cat,subcategory=sub,colors=colors,styles=[],formality_level=2)


def test_rules_fallback_builds_grounded_full_look_handoff(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    request=OutfitRequest(occasion="今天我想穿一身白色的衣服")
    handoff=understand_outfit_request(request,[])
    assert handoff["mode"]=="rules_fallback"
    assert handoff["model_call_count"]==0
    assert handoff["hard_constraints"][0]["kind"]=="full_look_color"
    assert handoff["hard_constraints"][0]["source_span"] in request.occasion


def test_specific_full_look_color_is_not_downgraded_to_generic_green(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    request=OutfitRequest(occasion="今天必须一身荧光绿")
    handoff=understand_outfit_request(request,[])
    assert handoff["hard_constraints"][0]["kind"]=="full_look_color"
    assert handoff["hard_constraints"][0]["value"]=="荧光绿"


def test_handoff_is_consumed_by_candidate_guard():
    handoff={"hard_constraints":[{"kind":"full_look_color","value":"白色","scope":"all_core_items","strength":"hard","source_span":"一身白色","confidence":.98}]}
    white=[item("top","上装","衬衫",["白色"]),item("bottom","下装","半身裙",["米白"]),item("shoe","鞋履","乐福鞋",["棕色"])]
    mixed=[item("top","上装","衬衫",["白色"]),item("bottom","下装","西裤",["深灰"]),item("shoe","鞋履","运动鞋",["白色"])]
    assert candidate_satisfies_handoff(white,handoff)
    assert not candidate_satisfies_handoff(mixed,handoff)


def test_followup_inherits_constraints_and_locks_non_shoe_items(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    wardrobe=[item("top","上装","衬衫",["白色"]),item("skirt","下装","半身裙",["米白"]),item("shoe","鞋履","乐福鞋",["棕色"])]
    previous=understand_outfit_request(OutfitRequest(occasion="今天想穿一身白色"),wardrobe)
    current=understand_outfit_request(OutfitRequest(occasion="这套鞋子换一双舒服点的"),wardrobe)
    merged=merge_conversation_context(current,previous,[{"item_ids":["top","skirt","shoe"]}],"这套鞋子换一双舒服点的",wardrobe)
    assert merged["conversation"]["is_contextual_followup"]
    assert merged["conversation"]["inherited_constraint_count"]==1
    assert set(merged["locked_item_ids"])=={"top","skirt"}
    assert "shoe" not in merged["locked_item_ids"]


def test_contextual_query_without_history_requests_clarification(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    current=understand_outfit_request(OutfitRequest(occasion="这套换双鞋"),[])
    merged=merge_conversation_context(current,None,[],"这套换双鞋",[])
    assert merged["needs_clarification"]
    assert merged["confidence"]["overall"]<=.72


def test_rules_extract_excluded_garment(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="今天不要穿裙子，也别穿高跟鞋"),[])
    excluded={(x["kind"],x["value"]) for x in handoff["hard_constraints"]}
    assert ("exclude_item","裙") in excluded
    assert ("exclude_item","高跟鞋") in excluded


def test_plain_degree_word_is_not_contextual_followup(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    current=understand_outfit_request(OutfitRequest(occasion="今天想正式一点"),[])
    merged=merge_conversation_context(current,None,[],"今天想正式一点",[])
    assert not merged["conversation"]["is_contextual_followup"]
    assert not merged["needs_clarification"]


def test_walking_comfort_is_enforced_by_candidate_guard(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="今天要走很多路"),[])
    base=[item("top","上装","衬衫",["白色"]),item("bottom","下装","西裤",["黑色"])]
    assert candidate_satisfies_handoff([*base,item("sneaker","鞋履","运动鞋",["白色"])],handoff)
    assert not candidate_satisfies_handoff([*base,item("heel","鞋履","高跟鞋",["黑色"])],handoff)


def test_followup_can_select_second_outfit(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    wardrobe=[item("top1","上装","衬衫",["白色"]),item("top2","上装","针织衫",["米白"]),item("bottom","下装","西裤",["黑色"]),item("shoe","鞋履","乐福鞋",["棕色"])]
    current=understand_outfit_request(OutfitRequest(occasion="第二套换双鞋"),wardrobe)
    merged=merge_conversation_context(current,{"hard_constraints":[]},[{"item_ids":["top1","bottom","shoe"]},{"item_ids":["top2","bottom","shoe"]}],"第二套换双鞋",wardrobe)
    assert "top2" in merged["locked_item_ids"]
    assert "top1" not in merged["locked_item_ids"]


def test_nearest_scope_hint_wins_for_color_and_garment(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="不要黑色上衣，但鞋子可以黑色"),[])
    black=next(x for x in handoff["hard_constraints"] if x["kind"]=="exclude_color")
    shoe=next(x for x in handoff["hard_constraints"] if x["value"]=="鞋履")
    assert black["scope"]=="top"
    assert shoe["scope"]=="shoes"


def test_formal_degree_phrase_is_soft_style_not_followup(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="今天想正式一点"),[])
    assert any(x["value"]=="正式一点" for x in handoff["soft_preferences"])


def test_typo_correction_is_auditable_and_drives_constraints(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="不要乐富鞋，想穿称衫"),[])
    assert handoff["original_query"]=="不要乐富鞋，想穿称衫"
    assert handoff["final_query"]=="不要乐福鞋，想穿衬衫"
    assert {(x["source"],x["target"]) for x in handoff["correction"]["edits"]}=={("乐富鞋","乐福鞋"),("称衫","衬衫")}
    constraints={(x["kind"],x["value"]) for x in handoff["hard_constraints"]}
    assert ("exclude_item","乐福鞋") in constraints
    assert ("include_item","衬衫") in constraints
    assert any(x["text"]=="不要" for x in handoff["correction"]["protected_spans"])


def test_numbers_times_and_negation_are_preserved_by_correction(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="14:00见客户，体感33℃，降雨99%，不要乐富鞋"),[])
    assert "14:00" in handoff["final_query"] and "33℃" in handoff["final_query"] and "99%" in handoff["final_query"]
    assert "不要乐福鞋" in handoff["final_query"]


def test_model_uses_one_strict_schema_call_with_original_text(monkeypatch):
    captured={}
    model_result={
        "correction":{"suggested_query":"想穿衬衫","edits":[{"source":"称衫","target":"衬衫","start":2,"end":4,"confidence":.99}]},
        "tasks":[{"role":"primary","action":"generate_outfit","intent":"outfit_generation","confidence":.95}],
        "entities":[{"text":"衬衫","type":"garment","normalized":"衬衫","confidence":.96,"start":2,"end":4,"source":"model"}],
        "relations":[],
        "constraints":[{"kind":"include_item","value":"衬衫","scope":"top","strength":"hard","source_span":"衬衫","confidence":.96}],
        "overall_confidence":.95,
        "reason":"识别完成",
    }

    class Completions:
        def create(self,**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(model_result,ensure_ascii=False)))])

    class Client:
        def __init__(self,**kwargs): self.chat=SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules,"openai",SimpleNamespace(OpenAI=Client))
    monkeypatch.setattr(settings,"openai_api_key","test-key")
    handoff=understand_outfit_request(OutfitRequest(occasion="想穿称衫"),[item("shirt","上装","衬衫",["白色"])])

    assert handoff["model_call_count"]==1
    assert handoff["final_query"]=="想穿衬衫"
    assert json.loads(captured["messages"][1]["content"])["user_text"]=="想穿称衫"
    assert captured["response_format"]["type"]=="json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["response_format"]["json_schema"]["schema"]==_strict_json_schema(StylingSemantics)


def test_profile_restriction_is_compiled_as_hard_constraint(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    profile=SimpleNamespace(restrictions=["不穿高跟鞋"])
    handoff=understand_outfit_request(OutfitRequest(occasion="今天通勤"),[],profile=profile)
    constraint=next(x for x in handoff["hard_constraints"] if x["value"]=="高跟鞋")
    assert constraint["kind"]=="exclude_item" and constraint["source"]=="profile"
    assert handoff["profile"]["compiled_restriction_count"]==1


def test_handoff_contains_relations_and_slots(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="不要黑色上衣，想穿衬衫",weather={"feels_like_c":33}),[])
    assert any(x["type"]=="negates" and x["target_text"]=="黑色" for x in handoff["relations"])
    assert "衬衫" in handoff["slots"]["garments"]["required"]
    assert "黑色" in handoff["slots"]["colors"]["excluded"]
    assert handoff["slots"]["weather"]["feels_like_c"]==33


def test_item_local_exclusions_are_applied_before_assembly(monkeypatch):
    monkeypatch.setattr(settings,"openai_api_key",None)
    handoff=understand_outfit_request(OutfitRequest(occasion="不要黑色，也不要高跟鞋"),[])
    inventory=[item("top","上装","衬衫",["白色"]),item("trousers","下装","西裤",["黑色"]),item("heel","鞋履","高跟鞋",["米白"]),item("shoe","鞋履","运动鞋",["白色"])]
    assert {x.id for x in prefilter_items_by_handoff(inventory,handoff)}=={"top","shoe"}
