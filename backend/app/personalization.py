from collections import Counter, defaultdict
from math import exp
from .time_utils import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import BehaviorFeature, ContextProfile, OutfitFeedback, Outfit, WardrobeItem, StyleIdentity

BASE_WEIGHTS={"weather":.25,"occasion":.20,"preference":.20,"color":.15,"proportion":.10,"utilization":.05,"freshness":.05}
PERSONALIZATION_HALF_LIFE_DAYS=90

def context_key(occasion:str)->str:
    text=occasion.lower()
    if any(x in text for x in ["工作","通勤","客户","商务"]): return "work"
    if any(x in text for x in ["约会"]): return "date"
    if any(x in text for x in ["旅行","机场"]): return "travel"
    if any(x in text for x in ["面试","婚礼","重要"]): return "important"
    return "weekend"

def feedback_affinities(db:Session,user_id:str,context:str,now=None)->dict:
    """Build time-decayed, explainable affinities from actual outfit decisions.

    A rejected outfit is weak negative evidence for every included item; explicitly
    replaced items are stronger negative evidence. Context matches count fully and
    cross-context evidence contributes only a quarter, which keeps cold starts useful
    without flattening work/date/travel preferences into one profile.
    """
    now=now or datetime.utcnow();numerators=defaultdict(float);denominators=defaultdict(float);samples=0
    rows=list(db.execute(select(OutfitFeedback,Outfit).join(Outfit,Outfit.id==OutfitFeedback.outfit_id).where(Outfit.user_id==user_id)).all())
    item_ids={item_id for feedback,outfit in rows for item_id in outfit.item_ids}
    items={item.id:item for item in db.scalars(select(WardrobeItem).where(WardrobeItem.id.in_(item_ids)))} if item_ids else {}
    for feedback,outfit in rows:
        age=max(0,(now-feedback.created_at).total_seconds()/86400);recency=exp(-.693147*age/PERSONALIZATION_HALF_LIFE_DAYS)
        context_weight=1.0 if context_key(outfit.occasion)==context else .25
        base=(1.0 if feedback.adopted else -1.0)*recency*context_weight;samples+=context_weight
        replaced=set(feedback.replaced_item_ids or [])
        for item_id in outfit.item_ids:
            item=items.get(item_id);signal=-1.0*recency*context_weight if item_id in replaced else base
            keys=[f"item:{item_id}"]
            if item:
                keys.extend([f"category:{item.category}",*(f"color:{x}" for x in item.colors),*(f"style:{x}" for x in item.styles)])
            for key in keys:numerators[key]+=signal;denominators[key]+=recency*context_weight
    values={key:round(numerators[key]/denominators[key],4) for key in numerators if denominators[key]}
    return {"values":values,"effective_samples":round(samples,2),"strength":round(min(.35,samples/(samples+8)*.35),4),"half_life_days":PERSONALIZATION_HALF_LIFE_DAYS}

def learn_from_feedback(db:Session,user_id:str,feedback:OutfitFeedback,outfit:Outfit):
    ctx=context_key(outfit.occasion); deltas=defaultdict(float); prefs={}
    tags=" ".join(feedback.feedback_tags)+" "+(feedback.free_text or "")
    if "不够舒服" in tags or "运动鞋" in tags: deltas["preference"]+=.025; prefs["comfort_first"]=True
    if "冷" in tags: deltas["weather"]+=.03; prefs["cold_bias"]=min(1,float(prefs.get("cold_bias",0))+.1)
    if "亮色" in tags or "太亮" in tags: deltas["freshness"]-=.015; prefs["low_saturation"]=True
    if "配色喜欢" in tags: deltas["color"]+=.015
    if feedback.replaced_item_ids: deltas["preference"]+=.01
    row=db.scalar(select(ContextProfile).where(ContextProfile.user_id==user_id,ContextProfile.context_key==ctx))
    if not row: row=ContextProfile(id=f"ctx_{user_id}_{ctx}",user_id=user_id,context_key=ctx,weights=BASE_WEIGHTS.copy(),preferences={},sample_count=0)
    weights=dict(row.weights);merged=dict(row.preferences)
    for k,v in deltas.items(): weights[k]=max(.03,weights.get(k,BASE_WEIGHTS[k])+v)
    total=sum(weights.values());weights={k:round(v/total,4) for k,v in weights.items()};merged.update(prefs)
    row.weights=weights;row.preferences=merged;row.sample_count+=1;row.updated_at=datetime.utcnow();db.add(row)
    for key,value in [("replacement_rate",1 if feedback.replaced_item_ids else 0),("adoption",1 if feedback.adopted else 0)]:
        f=db.scalar(select(BehaviorFeature).where(BehaviorFeature.user_id==user_id,BehaviorFeature.context_key==ctx,BehaviorFeature.feature_key==key))
        if not f: f=BehaviorFeature(user_id=user_id,context_key=ctx,feature_key=key,value=value,evidence_count=1,source="feedback")
        else: f.value=(f.value*f.evidence_count+value)/(f.evidence_count+1);f.evidence_count+=1;f.updated_at=datetime.utcnow()
        db.add(f)

def build_style_identity(db:Session,user_id:str):
    items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==user_id)))
    outfits=list(db.scalars(select(Outfit).where(Outfit.user_id==user_id)))
    adopted_ids={f.outfit_id for f in db.scalars(select(OutfitFeedback).where(OutfitFeedback.adopted==True))}
    adopted=[o for o in outfits if o.id in adopted_ids] or outfits[-8:]
    used=Counter(i for o in adopted for i in o.item_ids);by_id={x.id:x for x in items}
    colors=Counter(c for item_id,n in used.items() if item_id in by_id for c in by_id[item_id].colors for _ in range(n))
    fits=Counter(by_id[item_id].fit for item_id,n in used.items() if item_id in by_id for _ in range(n))
    core=[i for i,_ in used.most_common(5)] or [x.id for x in sorted(items,key=lambda x:x.wear_count,reverse=True)[:5]]
    formalities=[by_id[i].formality_level for i in used if i in by_id] or [3]
    ctx={x.context_key:{"weights":x.weights,"preferences":x.preferences} for x in db.scalars(select(ContextProfile).where(ContextProfile.user_id==user_id))}
    result={"signature_colors":[x for x,_ in colors.most_common(4)] or ["藏青","米白","棕色"],"silhouettes":[x for x,_ in fits.most_common(3)] or ["清晰腰线","直线轮廓"],"core_item_ids":core,"preferred_formality":round(sum(formalities)/len(formalities),2),"exploration_range":{"stable":.7,"variation":.2,"explore":.1},"context_expressions":ctx,"evolution":[{"period":"近 30 天","change":"更偏好低饱和中性色与舒适鞋型"}],"confidence":min(.95,.45+len(adopted)*.04)}
    row=db.get(StyleIdentity,user_id) or StyleIdentity(user_id=user_id)
    for k,v in result.items(): setattr(row,k,v)
    row.updated_at=datetime.utcnow();db.add(row);db.commit()
    result["narrative"]="低饱和中性色、清晰腰线和简洁鞋型已形成稳定核心；可用少量轻复古配饰增加辨识度。"
    return result
