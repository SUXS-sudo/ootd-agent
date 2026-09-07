import argparse,json,sys
from pathlib import Path
from types import SimpleNamespace as S

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"backend"))
from app.config import settings
from app.intent import merge_conversation_context,understand_outfit_request
from app.schemas import OutfitRequest

INVENTORY=[S(id="top_white",category="上装",subcategory="白色衬衫",colors=["白色"],styles=["通勤"]),S(id="top_knit",category="上装",subcategory="针织上衣",colors=["米白"],styles=["温柔"]),S(id="skirt",category="下装",subcategory="百褶半身裙",colors=["白色"],styles=["优雅"]),S(id="trousers",category="下装",subcategory="直筒西裤",colors=["黑色"],styles=["通勤"]),S(id="shoe",category="鞋履",subcategory="乐福鞋",colors=["棕色"],styles=["通勤"]),S(id="sneaker",category="鞋履",subcategory="运动鞋",colors=["白色"],styles=["休闲"]),S(id="outer",category="外套",subcategory="短款夹克",colors=["蓝色"],styles=["休闲"])]
PRIOR=[{"item_ids":["top_white","skirt","shoe","outer"]}]

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--mode",choices=["rules","model"],default="rules");parser.add_argument("--dataset",default=str(ROOT/"tests"/"evals"/"intent_frozen_v1.jsonl"));args=parser.parse_args()
    if args.mode=="rules": settings.openai_api_key=None
    cases=[json.loads(x) for x in Path(args.dataset).read_text(encoding="utf-8").splitlines() if x.strip()];passed=0;failures=[]
    for case in cases:
        previous=None
        if case.get("previous_query"): previous=understand_outfit_request(OutfitRequest(occasion=case["previous_query"]),INVENTORY)
        handoff=understand_outfit_request(OutfitRequest(occasion=case["query"]),INVENTORY);handoff=merge_conversation_context(handoff,previous,PRIOR,case["query"],INVENTORY)
        expected=case["expected"];hard=handoff.get("hard_constraints",[]);soft=handoff.get("soft_preferences",[]);ok=True
        ok&=set(expected.get("hard_kinds",[]))<={x["kind"] for x in hard};ok&=set(expected.get("soft_kinds",[]))<={x["kind"] for x in soft}
        values={x["value"] for x in hard+soft};ok&=all(any(v in actual or actual in v for actual in values) for v in expected.get("values",[]))
        for kind,value in expected.get("forbidden_hard",[]): ok&=not any(x["kind"]==kind and x["value"]==value for x in hard)
        for kind,scope in expected.get("scopes",{}).items(): ok&=any(x["kind"]==kind and x["scope"]==scope for x in hard)
        if "final_query" in expected: ok&=handoff.get("final_query")==expected["final_query"]
        protected={x["text"] for x in handoff.get("correction",{}).get("protected_spans",[])};ok&=set(expected.get("protected",[]))<=protected
        conv=handoff.get("conversation",{});ok&=conv.get("is_contextual_followup")==expected.get("contextual",False);ok&=conv.get("inherited_constraint_count",0)>=expected.get("inherited_min",0);ok&=len(handoff.get("locked_item_ids",[]))>=expected.get("locked_min",0)
        if ok: passed+=1
        else: failures.append({"id":case["id"],"handoff":handoff,"expected":expected})
    report={"dataset":Path(args.dataset).stem,"mode":args.mode,"total":len(cases),"passed":passed,"accuracy":round(passed/len(cases),4),"failures":failures}
    print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0 if not failures else 1)
if __name__=="__main__":main()
