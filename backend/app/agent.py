import json, time, uuid
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .config import settings
from .models import AgentRun, UserProfile
from .schemas import OutfitResult

class Decision(BaseModel): outfits:list[OutfitResult]

OUTFIT_ROLES=["主推荐","舒适备选","风格备选"]

DECISION_SCHEMA_HINT=json.dumps(Decision.model_json_schema(),ensure_ascii=False)
SYSTEM_PROMPT=f"""你是衣序的主 OOTD 造型决策模型。你负责语义理解和整体搭配决策，程序规则只提供真实衣物候选与最终安全校验。

先在内部完整理解用户的自然语言，不要只匹配关键词。区分并按以下优先级决策：
1. 明确要求与拒绝：例如“想穿裙子”“保留这件衬衫”“不要高跟鞋”是硬约束，每套都必须执行；
2. 现实可穿性：天气、温度、降雨、步行量、场合正式度和衣物当前状态；
3. 用户意图中的细腻风格：例如“温柔但不甜”“松弛但不能邋遢”“显精神”应转化为廓形、配色和正式度判断；
4. 长期偏好与穿着限制；
5. 配色、比例、衣橱利用率和适度新鲜感。

用户自然语言与表单默认值冲突时，以用户明确说出的信息为准。不要为了凑三套而忽略用户要求。候选无法真正满足时，在 warnings 中诚实指出具体冲突。
三套方案必须分别承担“主推荐”“舒适备选”“风格备选”的角色，并且是真正不同的决策，而非只改标题。主推荐覆盖全天行程；舒适备选侧重温度、步行和身体舒适并说明正式度取舍；风格备选侧重颜色、轮廓或配饰表达并说明全天适用性的取舍。reason 必须明确写出收益和代价；wearing_tips 给出当下能执行的穿法。
只能原样选择一整套候选组合，不能跨候选拼接、删减或发明 item_id。
禁止推断身体健康、体重、三围或敏感属性；不承诺精确尺码与未知面料效果。
输出要求：只输出一个 JSON 对象，不要任何额外文字、注释或 markdown 代码块标记；JSON 结构必须严格符合如下 Schema：
{DECISION_SCHEMA_HINT}
当证据不足时把问题写入 outfits[].warnings，不要猜测。"""

def rank_with_model(db:Session,user_id:str,candidates,context,fallback:list[OutfitResult],intent_handoff:dict|None=None):
    run_id=f"run_{uuid.uuid4().hex[:12]}"; start=time.perf_counter(); status="fallback"; error=None
    if not settings.openai_api_key:
        db.add(AgentRun(id=run_id,user_id=user_id,model=settings.openai_model,prompt_version="ootd-v2",status=status,error="OPENAI_API_KEY not configured")); db.commit(); return fallback,"rules"
    try:
        from openai import OpenAI
        client=OpenAI(api_key=settings.openai_api_key,base_url=settings.openai_base_url,timeout=settings.openai_ranking_timeout_seconds,max_retries=0)
        profile=db.get(UserProfile,user_id)
        profile_context={
            "preferred_styles": profile.preferred_styles,
            "avoided_styles": getattr(profile,"avoided_styles",[]),
            "preferred_item_terms": getattr(profile,"preferred_item_terms",[]),
            "avoided_item_terms": getattr(profile,"avoided_item_terms",[]),
            "preferred_colors": profile.preferred_colors,
            "avoided_colors": profile.avoided_colors,
            "restrictions": profile.restrictions,
            "visual_goals": profile.visual_goals,
            "temperature_preference": profile.temperature_preference,
        } if profile else {}
        payload={"user_request":context.model_dump(),"query_understanding_handoff":intent_handoff or {},"profile":profile_context,"candidates":[{"candidate_id":index,"item_ids":[x.id for x in items],"rule_scores":scores,"items":[{"item_id":x.id,"category":x.category,"subcategory":x.subcategory,"colors":x.colors,"styles":x.styles,"pattern":x.pattern,"fit":x.fit,"length":x.length,"warmth_level":x.warmth_level,"formality_level":x.formality_level,"weather_constraints":x.weather_constraints,"wear_count":x.wear_count} for x in items]} for index,(_,items,scores) in enumerate(candidates)]}
        response=client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user","content":json.dumps(payload,ensure_ascii=False)},
            ],
            response_format={"type":"json_object"},
            temperature=0.35,
            max_tokens=4096,
        )
        content=response.choices[0].message.content
        if not content: raise ValueError("empty model response")
        parsed=Decision.model_validate_json(content)
        allowed_combinations={frozenset(x.id for x in items) for _,items,_ in candidates}
        selected_combinations=[frozenset(o.item_ids) for o in parsed.outfits]
        selected_roles=[outfit.kind for outfit in parsed.outfits]
        if not parsed or len(parsed.outfits)!=3 or len(set(selected_combinations))!=3 or any(combo not in allowed_combinations for combo in selected_combinations): raise ValueError("model output must contain three distinct complete candidate combinations")
        if selected_roles!=OUTFIT_ROLES: raise ValueError("model output roles must be exactly: "+", ".join(OUTFIT_ROLES))
        status="succeeded"; result=parsed.outfits; source="model"
    except Exception as exc:
        error=str(exc)[:1000]; result=fallback; source="rules"
    latency=int((time.perf_counter()-start)*1000)
    db.add(AgentRun(id=run_id,user_id=user_id,model=settings.openai_model,prompt_version="ootd-v2",latency_ms=latency,status=status,error=error)); db.commit()
    return result,source
