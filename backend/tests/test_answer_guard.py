from types import SimpleNamespace

from app.answer_guard import build_evidence_pack,guard_outfit_answer
from app.ranking import deterministic_results


def item(id,cat,sub,color):
    return SimpleNamespace(id=id,category=cat,subcategory=sub,colors=[color],styles=[],formality_level=3,warmth_level=2)


def test_answer_guard_passes_grounded_results_and_builds_evidence():
    candidates=[]
    for index in range(3):
        items=[item(f"top{index}","上装","衬衫","白色"),item(f"bottom{index}","下装","半身裙","米白"),item(f"shoe{index}","鞋履","运动鞋","白色")]
        candidates.append((.9-index*.01,items,{"weather":.9,"occasion":.9,"preference":.9,"color":.9,"proportion":.9}))
    results=deterministic_results(candidates);by_id={x.id:x for _,items,_ in candidates for x in items};handoff={"hard_constraints":[{"kind":"full_look_color","value":"白色","scope":"all_core_items","strength":"hard","source_span":"一身白色","confidence":.98}]}
    guard=guard_outfit_answer(results,candidates,handoff,by_id)
    assert guard["status"]=="passed"
    assert len(build_evidence_pack(results,by_id))==3


def test_answer_guard_rejects_invented_or_constraint_breaking_result():
    white=[item("top","上装","衬衫","白色"),item("bottom","下装","半身裙","白色"),item("shoe","鞋履","运动鞋","白色")]
    candidates=[(.9,white,{"weather":.9,"occasion":.9,"preference":.9,"color":.9,"proportion":.9})]*3
    results=deterministic_results(candidates);results[0].item_ids=["invented"]
    guard=guard_outfit_answer(results,candidates,{"hard_constraints":[]},{x.id:x for x in white})
    assert guard["status"]=="failed"
    assert any("invented_item" in x for x in guard["violations"])


def test_answer_guard_rejects_duplicate_outfit_roles():
    candidates=[]
    for index in range(3):
        items=[item(f"top{index}","上装","衬衫","白色"),item(f"bottom{index}","下装","半身裙","米白"),item(f"shoe{index}","鞋履","运动鞋","白色")]
        candidates.append((.9-index*.01,items,{"weather":.9,"occasion":.9,"preference":.9,"color":.9,"proportion":.9}))
    results=deterministic_results(candidates);results[1].kind="主推荐"
    by_id={x.id:x for _,items,_ in candidates for x in items}
    guard=guard_outfit_answer(results,candidates,{"hard_constraints":[]},by_id)
    assert guard["status"]=="failed"
    assert "outfit_roles" in guard["violations"]
