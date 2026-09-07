import re
from itertools import product

from .schemas import OutfitRequest, OutfitResult
from .wardrobe_status import UNAVAILABLE_WARDROBE_STATUSES

UNAVAILABLE=UNAVAILABLE_WARDROBE_STATUSES
GROUPS={"top":{"上装"},"bottom":{"下装"},"dress":{"连衣裙"},"outer":{"外套"},"shoe":{"鞋履"}}
REQUIRED_ITEM_TERMS={"连衣裙":("连衣裙",),"裙子":("裙",),"半身裙":("半身裙",),"牛仔裤":("牛仔裤",),"西裤":("西裤",),"衬衫":("衬衫",),"针织":("针织",),"运动鞋":("运动鞋",),"乐福鞋":("乐福鞋",)}
NEGATIVE_PREFIXES=("不穿","不要","不想穿","别穿","避免")
COLOR_FAMILIES={"荧光绿":("荧光绿",),"白色":("白","米白","奶油","象牙","杏仁米"),"黑色":("黑","炭黑"),"蓝色":("蓝","藏青","海军蓝","靛蓝"),"绿色":("绿",),"红色":("红","酒红","豆沙粉"),"棕色":("棕","焦糖","驼","卡其"),"灰色":("灰","炭灰")}
FULL_LOOK_MARKERS=("一身","全身","全套","整套","从头到脚")
NEUTRAL_FAMILIES={"白色","黑色","棕色","灰色","蓝色"}


# 第一层：把用户在自然语言中明确覆盖的天气、活动和正式度写回结构化请求。
def resolve_request_context(request:OutfitRequest) -> OutfitRequest:
    text=" ".join([request.occasion,request.mood,*request.temporary_requirements])
    updates={}
    temperature=re.search(r"(-?\d{1,2})\s*(?:℃|度)",text)
    if temperature:
        value=max(-20,min(45,float(temperature.group(1))))
        updates["weather"]=request.weather.model_copy(update={"temperature_c":value,"feels_like_c":value})
    elif any(x in text for x in ("很热","炎热","高温","闷热")):
        updates["weather"]=request.weather.model_copy(update={"temperature_c":31,"feels_like_c":34})
    elif any(x in text for x in ("很冷","寒冷","降温","零下")):
        updates["weather"]=request.weather.model_copy(update={"temperature_c":8,"feels_like_c":6})
    weather=updates.get("weather",request.weather)
    if any(x in text for x in ("下雨","有雨","小雨","阵雨","雨天")):
        updates["weather"]=weather.model_copy(update={"rain_probability":max(.65,weather.rain_probability),"condition":"有雨"})
    elif any(x in text for x in ("没下雨","不下雨","无雨","晴天","大晴天")):
        updates["weather"]=weather.model_copy(update={"rain_probability":0.05,"condition":"晴"})
    walking=re.search(r"(?:走路|步行)\s*(\d+)\s*分钟",text)
    if walking: updates["walking_minutes"]=max(0,min(240,int(walking.group(1))))
    elif any(x in text for x in ("走路多","步行多","要走很多路","暴走")): updates["walking_minutes"]=60
    if any(x in text for x in ("面试","客户","正式会议","婚礼")): updates["formality_level"]=max(4,request.formality_level)
    elif any(x in text for x in ("居家","遛弯","休闲","随便穿")): updates["formality_level"]=min(2,request.formality_level)
    return request.model_copy(update=updates)


def required_item_terms(request:OutfitRequest):
    text=" ".join([request.occasion,request.mood,*request.temporary_requirements]);required=[]
    for term,matches in REQUIRED_ITEM_TERMS.items():
        if term in text and not any(f"{prefix}{term}" in text for prefix in NEGATIVE_PREFIXES) and matches not in required: required.append(matches)
    return required


def required_full_look_color(request:OutfitRequest):
    text=" ".join([request.occasion,request.mood,*request.temporary_requirements])
    if not any(marker in text for marker in FULL_LOOK_MARKERS): return None
    for color,family in COLOR_FAMILIES.items():
        if color in text and not any(f"{prefix}{color}" in text for prefix in NEGATIVE_PREFIXES): return color,family
    return None


def satisfies_required_items(items,request:OutfitRequest):
    required=required_item_terms(request)
    if not all(any(any(token in x.subcategory for token in matches) for x in items) for matches in required): return False
    color_requirement=required_full_look_color(request)
    if color_requirement:
        _,family=color_requirement;core=[x for x in items if x.category in {"上装","下装","外套","连衣裙"}]
        if not core or any(not any(any(token in color for token in family) for color in x.colors) for x in core): return False
    return True


# 第二层：只做真正的硬约束，避免用模糊分数把不可执行的衣服救回来。
def filter_items(items,request:OutfitRequest,profile):
    request=resolve_request_context(request);avoided=set(getattr(profile,"avoided_colors",[]) or []);avoided_styles=set(getattr(profile,"avoided_styles",[]) or []);avoided_terms=set(getattr(profile,"avoided_item_terms",[]) or []);result=[]
    for item in items:
        constraints=getattr(item,"weather_constraints",[]) or []
        if item.clean_status in UNAVAILABLE or avoided.intersection(item.colors): continue
        if avoided_styles.intersection(item.styles) or any(term in item.category or term in item.subcategory for term in avoided_terms): continue
        if request.weather.rain_probability>=.5 and any("不适合" in c and "雨" in c for c in constraints): continue
        if request.weather.rain_probability<.35 and any("仅雨天推荐" in c for c in constraints): continue
        if request.weather.feels_like_c>=29 and item.category=="外套" and item.warmth_level>=3: continue
        if request.weather.feels_like_c>=33 and item.category in {"上装","下装","连衣裙"} and item.warmth_level>=3: continue
        if request.formality_level>=5 and item.formality_level<2: continue
        result.append(item)
    return result


# 大衣橱先按请求做轻量预筛选，避免 50×50×50×50 的笛卡尔积。
def _limit_assembly_pool(items, request: OutfitRequest, per_group: int = 12):
    text=" ".join([request.occasion,*request.temporary_requirements]);locked=set(request.locked_item_ids)
    def priority(item):
        mentioned=4 if item.id in locked else 2 if item.subcategory in text or item.category in text else 0
        formality=max(0,1-abs(item.formality_level-request.formality_level)/4)
        target_warmth=3 if request.weather.feels_like_c<12 else 2 if request.weather.feels_like_c<25 else 1
        weather=max(0,1-abs(item.warmth_level-target_warmth)/4)
        return mentioned+formality*.5+weather*.35+1/(1+item.wear_count)*.15
    selected=[]
    for categories in GROUPS.values():
        group=[item for item in items if item.category in categories]
        selected.extend(sorted(group,key=priority,reverse=True)[:per_group])
    by_id={item.id:item for item in items}
    selected.extend(by_id[item_id] for item_id in locked if item_id in by_id)
    return list({item.id:item for item in selected}.values())


# 第三层：用穿着槽位模板组装完整套装，外套始终可选，连衣裙不会再叠加上下装。
def assemble_outfits(items,request:OutfitRequest):
    items=_limit_assembly_pool(items,request)
    buckets={key:[x for x in items if x.category in categories] for key,categories in GROUPS.items()};outers=[None,*buckets["outer"]];combos=[]
    if buckets["top"] and buckets["bottom"] and buckets["shoe"]:
        combos.extend([x for x in product(buckets["top"],buckets["bottom"],buckets["shoe"],outers)])
    if buckets["dress"] and buckets["shoe"]:
        combos.extend([(None,None,shoe,outer,dress) for dress,shoe,outer in product(buckets["dress"],buckets["shoe"],outers)])
    result=[]
    for combo in combos:
        chosen=[x for x in combo if x]
        if not set(request.locked_item_ids).issubset({x.id for x in chosen}) or not satisfies_required_items(chosen,request): continue
        if request.weather.feels_like_c<12 and buckets["outer"] and not any(x.category=="外套" for x in chosen): continue
        if request.weather.feels_like_c>=27 and request.weather.rain_probability<.35 and any(x.category=="外套" for x in chosen): continue
        result.append(chosen)
    return result


def _color_family(color):
    for family,tokens in COLOR_FAMILIES.items():
        if any(token in color for token in tokens): return family
    return color


def _weather_score(items,request):
    feels=request.weather.feels_like_c
    target=4.4 if feels<=5 else 3.6 if feels<=12 else 2.8 if feels<=18 else 2.0 if feels<=24 else 1.25 if feels<=29 else .7
    core=[x for x in items if x.category in {"上装","下装","连衣裙"}]
    outer=[x for x in items if x.category=="外套"]
    warmth=(sum(x.warmth_level for x in core)/max(1,len(core)))+(outer[0].warmth_level*.55 if outer else 0)
    return max(0,1-abs(warmth-target)/4)


def _color_score(items):
    families=[_color_family(c) for x in items for c in x.colors];unique=set(families)
    if len(unique)==1:return .96
    if len(unique)==2 and any(x in NEUTRAL_FAMILIES for x in unique):return .94
    if len(unique)==3 and sum(x in NEUTRAL_FAMILIES for x in unique)>=2:return .88
    if {"红色","绿色"}.issubset(unique):return .58
    return max(.55,.86-.09*max(0,len(unique)-2))


def _proportion_score(items):
    top=next((x for x in items if x.category=="上装"),None);bottom=next((x for x in items if x.category=="下装"),None);dress=next((x for x in items if x.category=="连衣裙"),None);outer=next((x for x in items if x.category=="外套"),None)
    score=.88
    if dress: score=.92 if getattr(dress,"fit","常规")!="宽松" else .84
    if top and bottom:
        if getattr(top,"fit","常规")=="宽松" and getattr(bottom,"fit","常规")=="宽松": score-=.16
        if getattr(top,"length","常规") in {"短款","常规"}: score+=.04
    if outer and getattr(outer,"length","常规")=="长款" and bottom and getattr(bottom,"length","常规")=="长款": score-=.1
    return max(.5,min(1,score))


def _preference_score(items,request,profile):
    styles=set(getattr(profile,"preferred_styles",[]) or []);colors=set(getattr(profile,"preferred_colors",[]) or []);preferred_terms=set(getattr(profile,"preferred_item_terms",[]) or []);item_styles={s for x in items for s in (getattr(x,"styles",[]) or [])};item_colors={c for x in items for c in x.colors}
    style_score=.72+min(.2,.08*len(styles&item_styles));color_score=.06 if colors&item_colors else 0;item_score=min(.12,.04*sum(any(term in item.category or term in item.subcategory for item in items) for term in preferred_terms))
    shoe=next((x for x in items if x.category=="鞋履"),None);comfort=0
    if request.walking_minutes>=30 and shoe:
        comfort=.12 if any(x in shoe.subcategory for x in ("运动鞋","帆布鞋","乐福鞋","平底鞋")) else -.18
    return max(.4,min(1,style_score+color_score+item_score+comfort))


# 第四层：整套评分。各维度都有真实计算，不再使用固定比例分或“越暖越好”。
def score_outfit(items,request,weights,profile=None):
    weather=_weather_score(items,request);occasion=sum(max(0,1-abs(x.formality_level-request.formality_level)/4) for x in items)/len(items);preference=_preference_score(items,request,profile);color=_color_score(items);proportion=_proportion_score(items)
    utilization=sum(.45+.55/(1+x.wear_count) for x in items)/len(items);freshness=sum(1/(1+x.wear_count) for x in items)/len(items)
    scores={"weather":weather,"occasion":occasion,"preference":preference,"color":color,"proportion":proportion,"utilization":utilization,"freshness":freshness}
    total=sum(weights.get(key,0)*value for key,value in scores.items())
    return total,scores


# 第五层：最大边际相关性重排，避免前三套只换一双鞋。
def diversify_candidates(scored,limit=36):
    # 多样性重排只需要处理高分候选；若遍历全部组合，大衣橱会在集合相似度计算上耗时过长。
    remaining=sorted(scored,key=lambda x:x[0],reverse=True)[:max(240,limit*6)];selected=[]
    while remaining and len(selected)<limit:
        if not selected: selected.append(remaining.pop(0));continue
        def value(candidate):
            ids={x.id for x in candidate[1]};core={x.id for x in candidate[1] if x.category in {"上装","下装","连衣裙"}}
            similarity=max(len(ids&{x.id for x in prior[1]})/len(ids|{x.id for x in prior[1]}) for prior in selected)
            core_similarity=max(len(core&{x.id for x in prior[1] if x.category in {"上装","下装","连衣裙"}})/max(1,len(core|{x.id for x in prior[1] if x.category in {"上装","下装","连衣裙"}})) for prior in selected)
            return candidate[0]-.14*similarity-.12*core_similarity
        best=max(range(len(remaining)),key=lambda i:value(remaining[i]));selected.append(remaining.pop(best))
    return selected


def generate_candidates(items,request:OutfitRequest,weights:dict|None=None,profile=None):
    request=resolve_request_context(request);weights=weights or {"weather":.25,"occasion":.20,"preference":.20,"color":.15,"proportion":.10,"utilization":.05,"freshness":.05}
    scored=[]
    for chosen in assemble_outfits(items,request):
        total,scores=score_outfit(chosen,request,weights,profile);scored.append((total,chosen,scores))
    return diversify_candidates(scored)

def personalize_candidates(candidates,signals:dict|None):
    """Blend general outfit quality with learned affinity, capped for safety."""
    if not signals or not signals.get("values") or signals.get("strength",0)<=0:return candidates
    affinities=signals["values"];strength=float(signals["strength"]);rescored=[]
    for total,items,scores in candidates:
        evidence=[]
        for item in items:
            keys=[f"item:{item.id}",f"category:{item.category}",*(f"color:{x}" for x in item.colors),*(f"style:{x}" for x in item.styles)]
            values=[affinities[key] for key in keys if key in affinities]
            if values:evidence.append(sum(values)/len(values))
        affinity=sum(evidence)/len(evidence) if evidence else 0
        normalized=(affinity+1)/2
        personalized_total=(1-strength)*total+strength*normalized
        rescored.append((personalized_total,items,{**scores,"personalization":round(normalized,4),"base_total":round(total,4)}))
    return diversify_candidates(rescored)


def deterministic_results(candidates,request=None):
    roles=["主推荐","舒适备选","风格备选"]
    remaining=list(candidates);selected=[]
    selectors=[lambda row:row[0],lambda row:.48*row[2]["weather"]+.32*row[2]["preference"]+.20*row[2]["occasion"],lambda row:.38*row[2]["color"]+.32*row[2]["proportion"]+.20*row[2]["preference"]+.10*row[0]]
    for selector in selectors:
        choice=max(remaining,key=selector);selected.append(choice);remaining.remove(choice)
    results=[]
    for index,(total,items,scores) in enumerate(selected):
        names="、".join(x.subcategory for x in items);colors=list(dict.fromkeys(c for x in items for c in x.colors));strongest=max((k for k in ("weather","occasion","preference","color","proportion")),key=lambda k:scores[k])
        labels={"weather":"体感温度适配","occasion":"场合正式度","preference":"个人偏好","color":"整套配色","proportion":"轮廓比例"}
        if index==0: tradeoff=f"最稳妥地覆盖当天行程，天气、场合和舒适度最均衡；优势是{labels[strongest]}。"
        elif index==1: tradeoff="更偏向步行与体感舒适，代价是正式感或造型表达比主推荐稍弱。"
        else: tradeoff="在配色和轮廓上更有表达，代价是全天通用性或舒适余量比主推荐稍低。"
        results.append(OutfitResult(title=f"{' × '.join(colors)}组合",kind=roles[index],item_ids=[x.id for x in items],reason=f"{tradeoff}{names}当前可穿，且未触发天气排除条件，综合评分 {total:.0%}。",color_guide=f"以{colors[0]}为主色，{colors[1] if len(colors)>1 else '同色系'}辅助。",wearing_tips=["根据室内外温差调整可选外层","优先保持鞋履与活动量匹配"],alternative_item_ids=[],scores={k:round(v,2) for k,v in scores.items()},warnings=[]))
    return results
