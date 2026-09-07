import uuid
from collections import Counter
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import WardrobeItem,PurchaseAnalysis
from .schemas import PurchaseCandidate,PurchaseResult

def analyze_purchase(db:Session,user_id:str,candidate:PurchaseCandidate)->PurchaseResult:
    items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==user_id)));same=[x for x in items if x.category==candidate.category]
    duplicate=max([.45*(len(set(x.colors)&set(candidate.colors))/max(1,len(set(candidate.colors))))+.35*(1 if x.subcategory in candidate.name else 0)+.2*(len(set(x.styles)&set(candidate.styles))/max(1,len(set(candidate.styles)))) for x in same] or [0])
    complementary=[x for x in items if x.category!=candidate.category and (set(x.styles)&set(candidate.styles) or set(x.colors).isdisjoint(candidate.colors))]
    compatibility=min(1,.35+len(complementary)*.08);count=min(30,max(0,len(complementary)*2-len(same)));category_counts=Counter(x.category for x in items);resolves_gap=category_counts[candidate.category]<2 and duplicate<.45
    decision="值得考虑" if compatibility>=.68 and duplicate<.55 else ("谨慎购买" if compatibility>=.45 else "建议跳过")
    idle=[]
    if duplicate>=.65:idle.append("与现有同品类、同色单品功能重叠")
    if compatibility<.5:idle.append("与当前核心颜色和风格连接较弱")
    if not candidate.styles:idle.append("风格用途信息不足，难判断实际使用场合")
    result=PurchaseResult(analysis_id=f"buy_{uuid.uuid4().hex[:10]}",decision=decision,duplication_score=round(duplicate,2),compatibility_score=round(compatibility,2),valid_outfit_count=count,resolves_gap=resolves_gap,best_color=candidate.colors[0] if candidate.colors else None,matching_item_ids=[x.id for x in complementary[:6]],idle_risks=idle,size_questions=["肩宽或腰围是否与常穿尺码一致？","退换规则是否允许实际试穿确认？"],explanation=f"预计可与现有衣橱形成约 {count} 套有效组合；判断目标是买回去是否真的会穿，而不是推动购买。")
    db.add(PurchaseAnalysis(id=result.analysis_id,user_id=user_id,candidate=candidate.model_dump(),result=result.model_dump(),decision=decision));db.commit();return result

def long_term_plan(db:Session,user_id:str):
    items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==user_id)));counts=Counter(x.category for x in items);low=[x.id for x in items if x.wear_count<3];repair=[x.id for x in items if x.clean_status=="需要修补"];storage=[x.id for x in items if x.clean_status=="季节性收纳"]
    return {"seasonal_storage":{"store_item_ids":storage,"reactivate_item_ids":[x.id for x in items if x.clean_status=="收纳中"]},"functional_gaps":["轻量防雨外层"] if not any("雨" in "".join(x.weather_constraints) for x in items) else [],"duplicate_warnings":[cat for cat,n in counts.items() if n>=5],"low_usage_item_ids":low,"care_actions":[{"item_id":x,"action":"安排修补后再进入推荐"} for x in repair],"future_events":["重要场合前 48 小时检查衣物状态"],"style_evolution":"稳定核心为低饱和中性色、清晰腰线和舒适鞋型；下一阶段以少量配饰探索为主。"}
