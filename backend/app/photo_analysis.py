import base64,json,re
from pathlib import Path
from openai import AsyncOpenAI
from .config import settings
from .schemas import AdvancedPhotoAnalysis

SYSTEM_PROMPT="""你是克制、可靠的女性穿搭视觉分析师。只分析图片中可见的服装、鞋、包、配色、轮廓、比例和层次，不推断体重、健康、年龄、种族、身份、吸引力或身体缺陷。建议必须能被图像观察支持；看不清就明确说看不清。优先给低成本、可立即执行的修改。只能引用提供的真实衣橱 item_id，不得编造单品。输出严格 JSON，不要 Markdown。"""

def _extract_json(text:str)->dict:
    text=text.strip();match=re.search(r"\{[\s\S]*\}",text)
    if not match:raise ValueError("视觉模型没有返回 JSON")
    return json.loads(match.group(0))

def _guard(data:dict,allowed_ids:set[str])->dict:
    violations=[];observations=data.get("observations") or []
    if not observations:violations.append("missing_visual_observations")
    for row in observations:
        if not isinstance(row,dict) or not row.get("evidence"):violations.append("unsupported_observation")
    ids=data.get("matched_wardrobe_item_ids") or []
    invented=[x for x in ids if x not in allowed_ids]
    if invented:violations.append("invented_wardrobe_item:"+",".join(invented))
    prohibited=" ".join(str(data.get(k,"")) for k in ("strongest_issue","expected_effect","change_cost"))
    if any(x in prohibited for x in ("体重","胖","瘦","年龄","疾病","健康")):violations.append("prohibited_sensitive_inference")
    return {"status":"passed" if not violations else "failed","violations":violations,"checked_claims":["visual_evidence","real_wardrobe_ids","no_sensitive_inference"]}

async def analyze_outfit_image(path:Path,wardrobe:list,occasion:str,weather:str)->AdvancedPhotoAnalysis:
    separate_vision_provider=bool(settings.openai_vision_base_url and settings.openai_vision_base_url.rstrip("/")!=settings.openai_base_url.rstrip("/"))
    key=settings.openai_vision_api_key if separate_vision_provider else (settings.openai_vision_api_key or settings.openai_api_key)
    if not key:raise RuntimeError("未配置视觉模型 API Key")
    model=settings.openai_vision_model or settings.openai_model
    base_url=settings.openai_vision_base_url or settings.openai_base_url
    mime={".png":"image/png",".webp":"image/webp"}.get(path.suffix.lower(),"image/jpeg")
    image_url=f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    wardrobe_context=[{"item_id":x.id,"category":x.category,"name":x.subcategory,"colors":x.colors,"styles":x.styles,"status":x.clean_status} for x in wardrobe]
    schema={"strongest_issue":"最值得调整的一处；若无需调整则说明","color":"可见配色分析","proportion":"只描述服装视觉比例","layering":"层次分析","accessories":"鞋包配饰分析","weather_fit":"与给定天气的适配","actionable_tips":["最多三条可执行建议"],"minimal_change":{"changes":1,"action":"只改一处","cost":"时间/操作成本"},"enhanced_change":{"changes":2,"actions":["两项修改"],"cost":"时间/操作成本"},"before_after":[{"item":"调整点","before":"当前可见效果","after":"预计效果","evidence":"图片中的可见依据"}],"change_cost":"总体修改成本","expected_effect":"预期视觉效果","observations":[{"claim":"观察结论","evidence":"图片中的具体可见区域","confidence":0.0}],"matched_wardrobe_item_ids":["仅在高度确定是衣橱同款时填写 item_id"],"prohibited_inferences":[],"deleted_after_analysis":True}
    prompt=f"场合：{occasion}；天气：{weather}。真实衣橱：{json.dumps(wardrobe_context,ensure_ascii=False)}。请分析图片并按此 JSON 结构返回：{json.dumps(schema,ensure_ascii=False)}"
    client=AsyncOpenAI(api_key=key,base_url=base_url)
    request={"model":model,"messages":[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":image_url,"detail":"high"}}]}],"temperature":.2,"max_tokens":1800}
    if model.lower().startswith("glm-"):request["extra_body"]={"thinking":{"type":"disabled"}}
    else:request["response_format"]={"type":"json_object"}
    response=await client.chat.completions.create(**request)
    data=_extract_json(response.choices[0].message.content or "")
    guard=_guard(data,{x.id for x in wardrobe});data["evidence_guard"]=guard
    if guard["status"]!="passed":raise ValueError("视觉分析证据检查失败："+",".join(guard["violations"]))
    data["deleted_after_analysis"]=True
    return AdvancedPhotoAnalysis.model_validate(data)
