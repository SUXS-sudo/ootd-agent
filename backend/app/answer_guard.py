from .intent import candidate_satisfies_handoff
from .ranking import COLOR_FAMILIES

OUTFIT_ROLES=["主推荐","舒适备选","风格备选"]


DIMENSION_LABELS={"weather":"天气适配","occasion":"场合适配","preference":"显式偏好","color":"配色协调","proportion":"轮廓比例","utilization":"衣橱利用","freshness":"穿着新鲜度","personalization":"历史反馈","base_total":"通用基线"}

def _dimension_evidence(dimension,score,items,request=None):
    refs=[x.id for x in items];facts=[]
    if dimension=="weather" and request:facts=[f"体感 {request.weather.feels_like_c:.0f}℃",f"降雨概率 {request.weather.rain_probability:.0%}",*[(f"{x.subcategory}保暖等级{x.warmth_level}") for x in items]]
    elif dimension=="occasion" and request:facts=[f"目标正式度 {request.formality_level}/5",*[(f"{x.subcategory}正式度{x.formality_level}/5") for x in items]]
    elif dimension=="color":facts=[f"{x.subcategory}：{'/'.join(x.colors)}" for x in items]
    elif dimension=="proportion":facts=[f"{x.subcategory}：{getattr(x,'fit','未标注版型')}、{getattr(x,'length','未标注长度')}" for x in items]
    elif dimension in {"utilization","freshness"}:facts=[f"{x.subcategory}累计穿着{getattr(x,'wear_count',0)}次" for x in items]
    elif dimension=="personalization":facts=["基于同场景为主、跨场景为辅的历史采用与拒绝记录；90天半衰期"]
    elif dimension=="preference":facts=[f"{x.subcategory}：{'/'.join(x.styles) or '未标注风格'}" for x in items]
    else:facts=[f"由{DIMENSION_LABELS.get(dimension,dimension)}规则计算"]
    confidence=round(min(.95,.55+.4*abs(float(score)-.5)*2),2)
    return {"dimension":dimension,"label":DIMENSION_LABELS.get(dimension,dimension),"score":score,"claim":f"{DIMENSION_LABELS.get(dimension,dimension)}得分 {score:.0%}","facts":facts,"source_refs":refs,"confidence":confidence,"method":"deterministic_rule" if dimension!="personalization" else "time_decayed_feedback"}

def build_evidence_pack(results,items_by_id:dict,request=None) -> list[dict]:
    pack=[]
    for index,result in enumerate(results,1):
        items=[items_by_id[x] for x in result.item_ids if x in items_by_id]
        dimensions=[_dimension_evidence(key,value,items,request) for key,value in result.scores.items()]
        pack.append({"evidence_id":f"O{index}","title":result.title,"item_ids":result.item_ids,"items":[{"item_id":x.id,"category":x.category,"subcategory":x.subcategory,"colors":x.colors,"styles":x.styles,"formality_level":x.formality_level,"warmth_level":x.warmth_level} for x in items],"scores":result.scores,"dimensions":dimensions,"limitations":["置信度表示证据完整度，不是统计校准后的成功概率"]})
    return pack


def guard_outfit_answer(results,candidates,handoff,items_by_id:dict) -> dict:
    allowed={frozenset(x.id for x in items) for _,items,_ in candidates}; violations=[]; seen=set()
    if len(results)!=3: violations.append("result_count")
    if [result.kind for result in results]!=OUTFIT_ROLES: violations.append("outfit_roles")
    for index,result in enumerate(results):
        ids=frozenset(result.item_ids)
        if ids in seen: violations.append(f"duplicate_outfit:{index}")
        seen.add(ids)
        if ids not in allowed: violations.append(f"unsupported_combination:{index}")
        if any(x not in items_by_id for x in result.item_ids): violations.append(f"invented_item:{index}")
        actual=[items_by_id[x] for x in result.item_ids if x in items_by_id]
        if not candidate_satisfies_handoff(actual,handoff): violations.append(f"hard_constraint:{index}")
        text=f"{result.title} {result.reason} {result.color_guide}"
        actual_colors=[color for item in actual for color in item.colors]
        for color,family in COLOR_FAMILIES.items():
            if color in text and not any(any(token in actual for token in family) for actual in actual_colors): violations.append(f"unsupported_color_claim:{index}:{color}")
    return {"status":"passed" if not violations else "failed","violations":violations,"checked_claims":["real_item_ids","complete_candidate","hard_constraints","distinct_results","distinct_outfit_roles","color_claim_evidence"],"retry_count":0}
