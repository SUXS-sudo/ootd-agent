import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from .config import settings
from .ranking import COLOR_FAMILIES, required_full_look_color
from .schemas import OutfitRequest


class StylingTask(BaseModel):
    role: Literal["primary", "auxiliary"]
    action: Literal["generate_outfit", "modify_outfit", "explain_outfit", "adjust_weather", "adjust_occasion", "adjust_comfort", "clarify"]
    intent: Literal["outfit_generation", "outfit_modification", "outfit_explanation", "weather_adjustment", "occasion_adjustment", "comfort_adjustment", "clarification"]
    confidence: float = Field(ge=0, le=1)


class CorrectionEdit(BaseModel):
    source: str = Field(min_length=1,max_length=20)
    target: str = Field(min_length=1,max_length=20)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    confidence: float = Field(ge=0,le=1)


class QueryCorrection(BaseModel):
    suggested_query: str = Field(max_length=500)
    edits: list[CorrectionEdit] = Field(default_factory=list,max_length=20)


class StylingEntity(BaseModel):
    text: str = Field(max_length=40)
    type: Literal["garment", "color", "style", "occasion", "weather", "activity", "comfort", "negation"]
    normalized: str = Field(max_length=40)
    confidence: float = Field(ge=0, le=1)
    start: int|None = Field(default=None,ge=0)
    end: int|None = Field(default=None,ge=0)
    source: Literal["rule","model","corrected_rule","profile","conversation"] = "model"


class StylingRelation(BaseModel):
    type: Literal["negates","locks","replaces","applies_to","modifies"]
    source_text: str = Field(max_length=60)
    target_text: str = Field(max_length=60)
    confidence: float = Field(ge=0,le=1)


class StylingConstraint(BaseModel):
    kind: Literal["include_item", "exclude_item", "include_color", "exclude_color", "full_look_color", "style", "occasion", "comfort"]
    value: str = Field(max_length=40)
    scope: Literal["any_item", "all_core_items", "top", "bottom", "outer", "shoes", "accessories", "whole_outfit"]
    strength: Literal["hard", "soft"]
    source_span: str = Field(max_length=60)
    confidence: float = Field(ge=0, le=1)


class StylingSemantics(BaseModel):
    correction: QueryCorrection
    tasks: list[StylingTask] = Field(min_length=1, max_length=5)
    entities: list[StylingEntity] = Field(default_factory=list, max_length=30)
    relations: list[StylingRelation] = Field(default_factory=list,max_length=30)
    constraints: list[StylingConstraint] = Field(default_factory=list, max_length=30)
    overall_confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=240)


INTENT_TO_ACTION={
    "outfit_generation":"generate_outfit",
    "outfit_modification":"modify_outfit",
    "outfit_explanation":"explain_outfit",
    "weather_adjustment":"adjust_weather",
    "occasion_adjustment":"adjust_occasion",
    "comfort_adjustment":"adjust_comfort",
    "clarification":"clarify",
}


SYSTEM_PROMPT="""你是穿搭系统的 QueryUnderstanding 模型，只负责理解用户说了什么，不负责推荐衣服或生成最终回答。
一次性提取：保守纠错建议、主任务/辅助任务、原文实体、实体关系、硬约束、软偏好。必须区分：
- “一身/全身/整套白色”是 full_look_color + all_core_items + hard；
- “想穿裙子/必须穿裙子”是 include_item + hard；
- “不要黑色/不穿裙子”是 exclude + hard；
- “温柔但不甜、松弛但利落”是 style + soft，并保留转折两侧语义；
- 步行多、怕冷、下雨是现实约束；用户明确表述优先于表单默认值。
纠错不得改变否定、数量、单位、时间、温度、概率或具体 item_id；每个 edit 必须带原文位置。每个 constraint.source_span 必须逐字来自最终查询；实体也必须能在最终查询中定位。不得发明用户没有说过的颜色、品类、场合或限制。
correction.suggested_query 是纠错后的最终查询；如果无需纠错，必须原样返回 user_text，并令 edits 为空。tasks、entities、relations 和 constraints 都必须基于该最终查询一次性生成。
只返回结构化结果，不要输出推荐、item_id、SQL、解释性正文或 markdown。"""


def _strict_json_schema(model:type[BaseModel]) -> dict:
    """Convert Pydantic's schema to the strict subset required by Structured Outputs."""
    schema=model.model_json_schema()

    def normalize(node):
        if isinstance(node,dict):
            if node.get("type")=="object" or "properties" in node:
                properties=node.get("properties",{})
                node["additionalProperties"]=False
                node["required"]=list(properties)
            for value in node.values(): normalize(value)
        elif isinstance(node,list):
            for value in node: normalize(value)

    normalize(schema)
    return schema


# 本地规则是明确业务信号的安全底座；模型只能补充，不能覆盖这些信号。
GARMENT_ALIASES={
    "连衣裙":("连衣裙","裙装"),"半身裙":("半身裙","长裙","短裙","百褶裙"),
    "裙":("裙子",),"牛仔裤":("牛仔裤","牛仔长裤"),"西裤":("西裤","正装裤"),
    "裤":("裤子","长裤","短裤","阔腿裤"),"衬衫":("衬衫","衬衣"),
    "针织":("针织衫","毛衣","针织"),"T恤":("T恤","t恤","T-shirt","tee"),
    "卫衣":("卫衣",),"外套":("外套","风衣","夹克","西装外套"),
    "运动鞋":("运动鞋","跑鞋","板鞋","小白鞋"),"乐福鞋":("乐福鞋",),
    "高跟鞋":("高跟鞋","细跟鞋"),"鞋履":("鞋子","鞋履"),
}
SCOPE_HINTS={"上衣":"top","上装":"top","裤":"bottom","裙":"bottom","下装":"bottom","外套":"outer","鞋":"shoes","包":"accessories","配饰":"accessories"}
NEGATION_TERMS=("不想穿","不要穿","不能穿","尽量别穿","不穿","别穿","不要","避免","拒绝")
STRONG_REFERENCE_TERMS=("这套","这个","这件","那个","上一套","刚才那套","第一套","第二套","第三套")
MODIFICATION_TERMS=("换一","换成","替换","保留","去掉","加件","加一件")
STYLE_PHRASES=("不要太正式","不太正式","温柔但不甜","松弛但利落","更正式","更休闲","正式一点","休闲一点","显精神","有气场","不要太甜","别太老气")
WALKING_PHRASES=("走路比较多","走路多","步行多","要走很多路","暴走","久走")
COMFORT_SHOE_TERMS=("运动鞋","跑鞋","板鞋","帆布鞋","乐福鞋","平底鞋","小白鞋")
TYPO_CORRECTIONS={"称衫":"衬衫","衬杉":"衬衫","乐富鞋":"乐福鞋","阔退裤":"阔腿裤","西妆":"西装","真织衫":"针织衫","玛丽真鞋":"玛丽珍鞋","显守":"显瘦","同勤":"通勤","放水":"防水"}
PROTECTED_PATTERN=re.compile(r"(?:不想穿|不要穿|不能穿|尽量别穿|不穿|别穿|不要|避免|拒绝|保留|只换)|(?:\d+(?:\.\d+)?\s*(?:℃|度|%|分钟|小时|点|件|套|双|cm|厘米))|(?:\d{1,2}:\d{2})|(?:item_[A-Za-z0-9_-]+)",re.IGNORECASE)


def _request_text(request: OutfitRequest) -> str:
    # 只把用户实际发送的场合文本和临时要求视为可做 source_span 校验的原文；
    # mood/weather 等表单默认值单独提供，不能伪装成用户亲口表达。
    return " ".join(x for x in [request.occasion, *request.temporary_requirements] if x).strip()


def _protected_spans(text:str) -> list[dict]:
    return [{"text":m.group(0),"start":m.start(),"end":m.end(),"kind":"protected"} for m in PROTECTED_PATTERN.finditer(text)]


def _replay_correction(text:str, edits:list[dict]) -> str|None:
    try:
        ordered=sorted(edits,key=lambda x:int(x["start"]));cursor=0;parts=[]
        for edit in ordered:
            start,end=int(edit["start"]),int(edit["end"])
            if start<cursor or end>len(text) or start>=end or text[start:end]!=edit["source"]: return None
            if any(start<span["end"] and end>span["start"] for span in _protected_spans(text)): return None
            parts.extend((text[cursor:start],str(edit["target"])));cursor=end
        parts.append(text[cursor:]);return "".join(parts)
    except Exception:
        return None


def _local_correction(text:str) -> dict:
    edits=[]
    for source,target in sorted(TYPO_CORRECTIONS.items(),key=lambda x:len(x[0]),reverse=True):
        for match in re.finditer(re.escape(source),text):
            if any(match.start()<x["end"] and match.end()>x["start"] for x in edits): continue
            if any(match.start()<x["end"] and match.end()>x["start"] for x in _protected_spans(text)): continue
            edits.append({"source":source,"target":target,"start":match.start(),"end":match.end(),"confidence":.99})
    for match in re.finditer(r"(?:一身|全身|全套|整套)\s*(百色)",text):
        start,end=match.start(1),match.end(1)
        if not any(start<x["end"] and end>x["start"] for x in edits): edits.append({"source":"百色","target":"白色","start":start,"end":end,"confidence":.96})
    corrected=_replay_correction(text,edits) or text
    return {"original_query":text,"final_query":corrected,"edits":sorted(edits,key=lambda x:x["start"]),"protected_spans":_protected_spans(text),"source":"local_dictionary" if edits else "unchanged","accepted":bool(edits)}


def _validate_model_correction(original:str, raw:dict|None, local:dict) -> dict:
    if not raw: return local
    try:
        proposal=QueryCorrection.model_validate(raw);edits=[x.model_dump() for x in proposal.edits]
        replayed=_replay_correction(original,edits)
        if replayed is None or replayed!=proposal.suggested_query: return local
        before=[x["text"] for x in _protected_spans(original)];after=[x["text"] for x in _protected_spans(replayed)]
        if before!=after or len(replayed)>max(500,int(len(original)*1.35)+8): return local
        return {"original_query":original,"final_query":replayed,"edits":edits,"protected_spans":_protected_spans(original),"source":"model_validated","accepted":bool(edits)}
    except Exception:
        return local


def _entity(text:str,entity_type:str,normalized:str,query:str,confidence:float,source:str="rule") -> dict:
    start=query.find(text);return {"text":text,"type":entity_type,"normalized":normalized,"confidence":confidence,"start":start if start>=0 else None,"end":start+len(text) if start>=0 else None,"source":source}


def _scope_for_span(text:str, start:int, fallback:str="any_item") -> str:
    left=max([text.rfind(separator,0,start) for separator in ("，",",","。","；",";","！","!","？","?")]+[-1])+1
    right_candidates=[position for separator in ("，",",","。","；",";","！","!","？","?") if (position:=text.find(separator,start))>=0]
    right=min(right_candidates) if right_candidates else len(text)
    candidates=[]
    for hint,scope in SCOPE_HINTS.items():
        for match in re.finditer(re.escape(hint),text[left:right]): candidates.append((abs(left+match.start()-start),-len(hint),scope))
    return min(candidates)[2] if candidates and min(candidates)[0]<=10 else fallback


def _negative_span(text:str, term:str) -> str|None:
    # 只把紧邻实体的否定视为该实体的作用域，避免“不是不要黑色”等双重否定。
    match=re.search(rf"({'|'.join(map(re.escape,NEGATION_TERMS))})\s*(?:任何|一件|一双|这种|这个)?\s*{re.escape(term)}",text)
    if not match or text[max(0,match.start()-2):match.start()] in {"不是","并非"}: return None
    return match.group(0)


def _append_unique(target:list[dict], value:dict) -> None:
    key=(value.get("kind"),value.get("value"),value.get("scope"))
    if not any((x.get("kind"),x.get("value"),x.get("scope"))==key for x in target): target.append(value)


def _fallback(request: OutfitRequest, correction:dict|None=None) -> dict:
    correction=correction or _local_correction(_request_text(request));text=correction["final_query"]; constraints=[]; entities=[]
    corrected_request=request.model_copy(update={"occasion":text,"temporary_requirements":[]})
    color=required_full_look_color(corrected_request)
    if color:
        name,_=color; span=next((f"{marker}{name}" for marker in ("一身","全身","全套","整套","从头到脚") if f"{marker}{name}" in text),name)
        constraints.append({"kind":"full_look_color","value":name,"scope":"all_core_items","strength":"hard","source_span":span,"confidence":.98})
        entities.append({"text":name,"type":"color","normalized":name,"confidence":.98})
    occupied=[]
    alias_rows=sorted(((alias,canonical) for canonical,aliases in GARMENT_ALIASES.items() for alias in aliases),key=lambda x:len(x[0]),reverse=True)
    for alias,value in alias_rows:
        for match in re.finditer(re.escape(alias),text,re.IGNORECASE):
            if any(match.start()<end and match.end()>start for start,end in occupied): continue
            negative=_negative_span(text,match.group(0));kind="exclude_item" if negative else "include_item"
            default_scope="shoes" if value in {"运动鞋","乐福鞋","高跟鞋","鞋履"} else "outer" if value=="外套" else "bottom" if value in {"连衣裙","半身裙","裙","牛仔裤","西裤","裤"} else "top"
            scope=_scope_for_span(text,match.start(),default_scope)
            source=negative or match.group(0)
            _append_unique(constraints,{"kind":kind,"value":value,"scope":scope,"strength":"hard","source_span":source,"confidence":.96 if negative else .95})
            entities.append({"text":match.group(0),"type":"garment","normalized":value,"confidence":.95})
            if negative: entities.append({"text":negative,"type":"negation","normalized":"排除","confidence":.96})
            occupied.append((match.start(),match.end()))
            break
    if not color:
        for name,family in COLOR_FAMILIES.items():
            token=next((token for token in sorted(set((name,*family)),key=len,reverse=True) if token in text),None)
            if not token: continue
            negative=_negative_span(text,token);kind="exclude_color" if negative else "include_color";span=negative or token
            scope=_scope_for_span(text,text.index(token))
            _append_unique(constraints,{"kind":kind,"value":name,"scope":scope,"strength":"hard","source_span":span,"confidence":.96 if negative else .94});entities.append({"text":token,"type":"color","normalized":name,"confidence":.94})
    soft=[]
    for phrase in STYLE_PHRASES:
        if phrase in text: soft.append({"kind":"style","value":phrase,"scope":"whole_outfit","strength":"soft","source_span":phrase,"confidence":.9});entities.append({"text":phrase,"type":"style","normalized":phrase,"confidence":.9})
    for phrase in WALKING_PHRASES:
        if phrase in text: constraints.append({"kind":"comfort","value":"步行舒适","scope":"shoes","strength":"hard","source_span":phrase,"confidence":.95});entities.append({"text":phrase,"type":"comfort","normalized":"步行舒适","confidence":.95});break
    contextual=any(x in text for x in STRONG_REFERENCE_TERMS) or any(x in text for x in MODIFICATION_TERMS)
    intent="outfit_modification" if contextual else "outfit_generation";action="modify_outfit" if contextual else "generate_outfit"
    tasks=[{"role":"primary","action":action,"intent":intent,"confidence":.9 if contextual else .86}]
    auxiliary=[]
    if any(x in text for x in ("下雨","雨天","高温","很热","很冷","降温","体感")): auxiliary.append(("adjust_weather","weather_adjustment"))
    if any(x in text for x in ("客户","会议","面试","婚礼","通勤","约会","晚餐")): auxiliary.append(("adjust_occasion","occasion_adjustment"))
    if any(x in text for x in (*WALKING_PHRASES,"舒服","怕冷","怕热","磨脚")): auxiliary.append(("adjust_comfort","comfort_adjustment"))
    if any(x in text for x in ("为什么","依据","怎么推荐","解释")): auxiliary.append(("explain_outfit","outfit_explanation"))
    for auxiliary_action,auxiliary_intent in auxiliary:
        if auxiliary_intent!=intent: tasks.append({"role":"auxiliary","action":auxiliary_action,"intent":auxiliary_intent,"confidence":.9})
    result={"mode":"rules_fallback","model_call_count":0,"correction":correction,"original_query":correction["original_query"],"final_query":text,"valid_sections":["correction","tasks","entities","constraints","relations","slots"],"section_sources":{"correction":correction["source"],"tasks":"rules","entities":"rules","constraints":"rules","relations":"rules","slots":"rules"},"tasks":tasks[:5],"entities":entities,"relations":_build_relations(text,constraints),"hard_constraints":constraints,"soft_preferences":soft,"slots":_build_slots(request,constraints,soft),"overall_confidence":min([x["confidence"] for x in constraints] or [.72]),"reason":"本地规则回退"}
    return _detect_conflicts(result)


def _detect_conflicts(result:dict) -> dict:
    constraints=result.get("hard_constraints",[]); conflicts=[]
    for left in constraints:
        for right in constraints:
            opposed={("include_item","exclude_item"),("include_color","exclude_color"),("full_look_color","exclude_color")}
            if (left.get("kind"),right.get("kind")) in opposed and left.get("value")==right.get("value") and left.get("scope")==right.get("scope"):
                conflict={"value":left.get("value"),"scope":left.get("scope"),"source_spans":[left.get("source_span"),right.get("source_span")]}
                if conflict not in conflicts: conflicts.append(conflict)
    result["constraint_conflicts"]=conflicts
    return result


def _build_relations(text:str,constraints:list[dict]) -> list[dict]:
    relations=[]
    for constraint in constraints:
        kind=constraint.get("kind","");span=constraint.get("source_span","");value=constraint.get("value","")
        relation="negates" if kind.startswith("exclude") else "locks" if kind.startswith("include") or kind=="full_look_color" else "modifies"
        relations.append({"type":relation,"source_text":span,"target_text":value,"confidence":constraint.get("confidence",.8)})
    return relations


def _build_slots(request:OutfitRequest,hard:list[dict],soft:list[dict]) -> dict:
    return {
        "garments":{"required":[x["value"] for x in hard if x["kind"]=="include_item"],"excluded":[x["value"] for x in hard if x["kind"]=="exclude_item"],"locked_item_ids":[]},
        "colors":{"required":[x["value"] for x in hard if x["kind"] in {"include_color","full_look_color"}],"excluded":[x["value"] for x in hard if x["kind"]=="exclude_color"]},
        "weather":request.weather.model_dump(),
        "occasion":{"text":request.occasion,"formality_level":request.formality_level},
        "activity":{"walking_minutes":request.walking_minutes,"indoor_ratio":request.indoor_ratio},
        "styles":{"preferred":[x["value"] for x in soft if x["kind"]=="style"]},
    }


def understand_outfit_request(request: OutfitRequest, wardrobe_items, allow_model: bool = True, profile=None) -> dict:
    original=_request_text(request);local_correction=_local_correction(original);text=local_correction["final_query"]
    if not allow_model or not settings.openai_api_key:
        result=_fallback(request,local_correction);return _merge_profile_constraints(result,profile)
    try:
        from openai import OpenAI
        catalog=[{"category":x.category,"subcategory":x.subcategory,"colors":x.colors,"styles":x.styles} for x in wardrobe_items]
        client=OpenAI(api_key=settings.openai_api_key,base_url=settings.openai_base_url,max_retries=0)
        schema=_strict_json_schema(StylingSemantics)
        response=client.chat.completions.create(model=settings.openai_model,messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":json.dumps({"user_text":original,"chat_history":request.chat_history[-8:],"structured_defaults":request.model_dump(exclude={"chat_history"}),"wardrobe_vocabulary":catalog},ensure_ascii=False)}],response_format={"type":"json_schema","json_schema":{"name":"query_understanding","strict":True,"schema":schema}},temperature=.1,max_tokens=2400)
        raw=json.loads(response.choices[0].message.content or "{}")
        correction=_validate_model_correction(original,raw.get("correction"),local_correction);text=correction["final_query"]
        fallback=_fallback(request,correction); valid_sections=["correction"]; section_sources={"correction":correction["source"]}
        try:
            tasks=[StylingTask.model_validate(x) for x in raw.get("tasks",[])]
            if not 1<=len(tasks)<=5 or sum(t.role=="primary" for t in tasks)!=1 or any(INTENT_TO_ACTION[t.intent]!=t.action for t in tasks): raise ValueError("invalid tasks")
            valid_sections.append("tasks");section_sources["tasks"]="model_validated"
        except Exception:
            tasks=[StylingTask.model_validate(x) for x in fallback["tasks"]]
            section_sources["tasks"]="rules_fallback"
        valid_entities=[]
        try:
            entities=[StylingEntity.model_validate(x) for x in raw.get("entities",[])]
            valid_entities=[]
            for entity in entities:
                start=text.find(entity.text)
                if start<0: continue
                data=entity.model_dump();data.update(start=start,end=start+len(entity.text),source="model");valid_entities.append(data)
            # 明确规则实体作为底座，模型只补充原文可验证实体。
            for item in fallback["entities"]:
                if not any(x["text"]==item["text"] and x["type"]==item["type"] for x in valid_entities): valid_entities.append(item)
            valid_sections.append("entities");section_sources["entities"]="model_plus_rules"
        except Exception:
            valid_entities=fallback["entities"]
            section_sources["entities"]="rules_fallback"
        valid_constraints=[]
        try:
            constraints=[StylingConstraint.model_validate(x) for x in raw.get("constraints",[])]
            catalog_terms={x.category for x in wardrobe_items}|{x.subcategory for x in wardrobe_items}
            for constraint in constraints:
                if constraint.source_span not in text: continue
                if constraint.kind in {"include_color","exclude_color","full_look_color"} and constraint.value not in COLOR_FAMILIES: continue
                if constraint.kind in {"include_item","exclude_item"} and not any(constraint.value in term or term in constraint.value for term in catalog_terms): continue
                data=constraint.model_dump()
                if data["kind"]=="comfort" and any(x in data["source_span"] for x in ("走","步行","久站","舒服")):
                    data.update(value="步行舒适",scope="shoes",strength="hard")
                if data["kind"]=="style": data["strength"]="soft"
                valid_constraints.append(data)
            for item in fallback["hard_constraints"]+fallback["soft_preferences"]:
                _append_unique(valid_constraints,item)
            valid_sections.append("constraints");section_sources["constraints"]="model_plus_rules"
        except Exception:
            valid_constraints=fallback["hard_constraints"]+fallback["soft_preferences"]
            section_sources["constraints"]="rules_fallback"
        hard=[x for x in valid_constraints if x["strength"]=="hard"]
        soft=[x for x in valid_constraints if x["strength"]=="soft"]
        overall=float(raw.get("overall_confidence",.7)); overall=max(0,min(1,overall))
        # 明确的本地修改信号拥有最终任务边界裁决权。
        if fallback["tasks"][0]["intent"]=="outfit_modification": tasks=[StylingTask.model_validate(fallback["tasks"][0])]
        relations=[]
        try:
            relations=[x.model_dump() for x in [StylingRelation.model_validate(x) for x in raw.get("relations",[])] if x.source_text in text and x.target_text in text]
            valid_sections.append("relations");section_sources["relations"]="model_validated"
        except Exception:
            section_sources["relations"]="rules_fallback"
        for relation in _build_relations(text,hard+soft):
            if relation not in relations: relations.append(relation)
        result={"mode":"single_structured_call","model_call_count":1,"correction":correction,"original_query":original,"final_query":text,"valid_sections":valid_sections+["slots"],"section_sources":{**section_sources,"slots":"deterministic"},"tasks":[x.model_dump() for x in tasks],"entities":valid_entities,"relations":relations,"hard_constraints":hard,"soft_preferences":soft,"slots":_build_slots(request,hard,soft),"overall_confidence":overall,"reason":str(raw.get("reason","") or "统一语义理解完成")[:240]}
        return _merge_profile_constraints(calibrate_confidence(_detect_conflicts(result)),profile)
    except Exception as exc:
        result=_fallback(request,local_correction); result["fallback_error"]=str(exc)[:300]; return _merge_profile_constraints(calibrate_confidence(result),profile)


REFERENCE_TERMS=STRONG_REFERENCE_TERMS+MODIFICATION_TERMS
NEW_REQUEST_TERMS=("重新搭配","重新推荐","换个主题","新的一套")

def _merge_profile_constraints(handoff:dict,profile) -> dict:
    if not profile: return calibrate_confidence(_detect_conflicts(handoff))
    profile_text=" ".join(getattr(profile,"restrictions",[]) or [])
    if profile_text:
        profile_request=OutfitRequest(occasion=profile_text)
        profile_result=_fallback(profile_request,_local_correction(profile_text))
        for constraint in profile_result.get("hard_constraints",[]):
            if constraint["kind"] not in {"exclude_item","exclude_color"}: continue
            constraint={**constraint,"source":"profile","confidence":.99}
            _append_unique(handoff.setdefault("hard_constraints",[]),constraint)
    handoff.setdefault("profile",{})["compiled_restriction_count"]=sum(x.get("source")=="profile" for x in handoff.get("hard_constraints",[]))
    handoff["slots"]=_build_slots(OutfitRequest(),handoff.get("hard_constraints",[]),handoff.get("soft_preferences",[]))|{k:v for k,v in handoff.get("slots",{}).items() if k in {"weather","occasion","activity"}}
    return calibrate_confidence(_detect_conflicts(handoff))

def merge_conversation_context(current:dict,previous:dict|None,last_outfits:list,query:str,wardrobe_items) -> dict:
    previous=previous or {}; is_reference=any(x in query for x in REFERENCE_TERMS) and not any(x in query for x in NEW_REQUEST_TERMS)
    inherited=[]; locked=[]
    if is_reference and previous:
        current_keys={(x.get("kind"),x.get("scope")) for x in current.get("hard_constraints",[])}
        inherited=[x for x in previous.get("hard_constraints",[]) if (x.get("kind"),x.get("scope")) not in current_keys]
        current["hard_constraints"]=[*inherited,*current.get("hard_constraints",[])]
        if last_outfits:
            selected_index=next((index for token,index in (("第一套",0),("第二套",1),("第三套",2)) if token in query),0)
            selected_index=min(selected_index,len(last_outfits)-1)
            prior_ids=list(last_outfits[selected_index].get("item_ids",[])); by_id={x.id:x for x in wardrobe_items}
            replace_categories=set()
            if "鞋" in query: replace_categories.add("鞋履")
            if "上衣" in query or "上装" in query: replace_categories.add("上装")
            if "裤" in query or "裙" in query or "下装" in query: replace_categories.add("下装")
            if "外套" in query: replace_categories.add("外套")
            if "包" in query: replace_categories.update({"包袋","配饰"})
            if "换" in query or "替换" in query:
                locked=[item_id for item_id in prior_ids if item_id in by_id and by_id[item_id].category not in replace_categories]
    current["conversation"]={"is_contextual_followup":is_reference,"inherited_constraint_count":len(inherited),"locked_item_ids":locked,"history_used":bool(previous)}
    current["locked_item_ids"]=locked
    return calibrate_confidence(_detect_conflicts(current))

def calibrate_confidence(handoff:dict) -> dict:
    tasks=handoff.get("tasks",[]); entities=handoff.get("entities",[]); hard=handoff.get("hard_constraints",[]); soft=handoff.get("soft_preferences",[])
    task=min([float(x.get("confidence",0)) for x in tasks] or [0.5])
    entity=min([float(x.get("confidence",0)) for x in entities] or [0.72])
    hard_score=min([float(x.get("confidence",0)) for x in hard] or [0.9])
    slot_types={x.get("type") for x in entities}; slots={slot:round(min([float(x.get("confidence",0)) for x in entities if x.get("type")==slot] or [0]),3) for slot in ("garment","color","style","occasion","weather","activity","comfort","negation")}
    valid_ratio=min(1,len(handoff.get("valid_sections",[]))/6)
    schema=round(.55+.45*valid_ratio,3)
    components=[task,schema]
    if entities: components.append(entity)
    if hard: components.append(hard_score)
    overall=min(components)
    if handoff.get("mode")=="rules_fallback": overall=min(overall,.72)
    handoff["confidence"]={"overall":round(overall,3),"task":round(task,3),"entity":round(entity,3),"hard_filters":round(hard_score,3),"schema":schema,"slots":slots}
    handoff["overall_confidence"]=round(overall,3)
    handoff["needs_clarification"]=bool(handoff.get("constraint_conflicts")) or overall<.55 or (handoff.get("conversation",{}).get("is_contextual_followup") and not handoff.get("conversation",{}).get("history_used"))
    if handoff.get("constraint_conflicts"):
        values="、".join(dict.fromkeys(str(x.get("value")) for x in handoff["constraint_conflicts"]))
        handoff["clarification"]={"reason":"constraint_conflict","question":f"你对{values}同时表达了保留和排除，请确认最终希望保留还是排除。","required":True}
    elif handoff.get("conversation",{}).get("is_contextual_followup") and not handoff.get("conversation",{}).get("history_used"):
        handoff["clarification"]={"reason":"missing_reference","question":"我知道你在修改上一套，但当前没有可定位的上一套穿搭；请指出要修改的方案或具体单品。","required":True}
    elif overall<.55:
        handoff["clarification"]={"reason":"low_confidence","question":"我还不能可靠确定你的穿搭要求，请补充要保留、排除或调整的具体内容。","required":True}
    else:
        handoff["clarification"]={"required":False}
    return handoff


def candidate_satisfies_handoff(items, handoff: dict) -> bool:
    if not set(handoff.get("locked_item_ids",[])).issubset({x.id for x in items}): return False
    for constraint in handoff.get("hard_constraints",[]):
        kind=constraint["kind"]; value=constraint["value"]; scope=constraint["scope"]
        scoped=list(items)
        category={"top":"上装","bottom":"下装","outer":"外套","shoes":"鞋履","accessories":"配饰"}.get(scope)
        if category: scoped=[x for x in items if x.category==category or scope=="accessories" and x.category=="包袋"]
        if kind=="full_look_color": scoped=[x for x in items if x.category in {"上装","下装","外套"}]
        if kind in {"include_color","full_look_color"}:
            family=COLOR_FAMILIES.get(value,(value,))
            checks=[any(any(token in color for token in family) for color in x.colors) for x in scoped]
            if not checks or (kind=="full_look_color" and not all(checks)) or (kind=="include_color" and not any(checks)): return False
        elif kind=="exclude_color":
            family=COLOR_FAMILIES.get(value,(value,))
            if any(any(any(token in color for token in family) for color in x.colors) for x in scoped): return False
        elif kind=="include_item" and not any(value in x.category or value in x.subcategory or x.subcategory in value for x in scoped): return False
        elif kind=="exclude_item" and any(value in x.category or value in x.subcategory or x.subcategory in value for x in scoped): return False
        elif kind=="comfort" and value=="步行舒适":
            shoes=[x for x in scoped if x.category=="鞋履"] if scope!="shoes" else scoped
            if not shoes or not all(any(term in x.subcategory for term in COMFORT_SHOE_TERMS) or "舒适" in (getattr(x,"styles",[]) or []) for x in shoes): return False
        elif kind=="occasion":
            levels=[getattr(x,"formality_level",None) for x in scoped]
            known=[x for x in levels if x is not None]
            if value in {"正式","商务","面试","婚礼"} and (not known or sum(known)/len(known)<2.5): return False
            if value in {"休闲","居家"} and (not known or sum(known)/len(known)>3.5): return False
    return True


def prefilter_items_by_handoff(items, handoff:dict):
    """Apply item-local hard exclusions before outfit assembly; complete-look rules run again afterward."""
    result=[]
    for item in items:
        rejected=False
        for constraint in handoff.get("hard_constraints",[]):
            kind,value,scope=constraint.get("kind"),constraint.get("value"),constraint.get("scope")
            category={"top":"上装","bottom":"下装","outer":"外套","shoes":"鞋履","accessories":"配饰"}.get(scope)
            if category and item.category!=category and not (scope=="accessories" and item.category=="包袋"): continue
            if kind=="exclude_item" and (value in item.category or value in item.subcategory or item.subcategory in value): rejected=True;break
            if kind=="exclude_color":
                family=COLOR_FAMILIES.get(value,(value,))
                if any(any(token in color for token in family) for color in item.colors): rejected=True;break
        if not rejected: result.append(item)
    return result
