import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import WardrobeItem,UserProfile,WeeklyPlan,PlanDay,TravelPlan,MultiScenePlan
from .schemas import WeeklyPlanRequest,WeeklyPlanResult,DayPlan,ReplanRequest,TravelPlanRequest,TravelPlanResult,MultiSceneRequest,MultiSceneResult,OutfitRequest
from .ranking import filter_items,generate_candidates

def _pick(db,user_id,day,locked=None,excluded=None):
    items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==user_id)));profile=db.get(UserProfile,user_id);request=OutfitRequest(occasion=day.occasion,formality_level=day.formality_level,weather=day.weather,locked_item_ids=locked or [])
    candidates=generate_candidates(filter_items(items,request,profile),request,profile=profile)
    excluded=set(excluded or [])
    chosen=next((c for c in candidates if tuple(sorted(x.id for x in c[1])) not in excluded),candidates[0] if candidates else None)
    if not chosen:return []
    return [x.id for x in chosen[1]]

def create_weekly_plan(db:Session,user_id:str,body:WeeklyPlanRequest)->WeeklyPlanResult:
    plan_id=f"week_{uuid.uuid4().hex[:10]}";seen=set();days=[];usage={}
    for day in body.days:
        ids=_pick(db,user_id,day,excluded=seen);seen.add(tuple(sorted(ids)))
        for x in ids:usage.setdefault(x,[]).append(day.date)
        days.append(DayPlan(date=day.date,occasion=day.occasion,item_ids=ids,weather=day.weather,reason="兼顾天气、日程、整周轮换与已有衣物复用。",reuse_notes=[],warnings=[] if ids else ["可用衣物不足"]))
    for d in days:d.reuse_notes=[f"{x} 在本周复用 {len(usage[x])} 次" for x in d.item_ids if len(usage[x])>1]
    capsule=sorted(usage,key=lambda x:(-len(usage[x]),x));color_story=["周初低饱和通勤","周中色彩轻变化","周末放松轮廓"]
    db.add(WeeklyPlan(id=plan_id,user_id=user_id,start_date=body.start_date,version=1,summary={"capsule_item_ids":capsule,"color_story":color_story}))
    for d in days:db.add(PlanDay(id=f"day_{uuid.uuid4().hex[:10]}",plan_id=plan_id,date=d.date,occasion=d.occasion,weather=d.weather.model_dump(),item_ids=d.item_ids,explanation={"reason":d.reason,"reuse_notes":d.reuse_notes}))
    db.commit();return WeeklyPlanResult(plan_id=plan_id,version=1,days=days,capsule_item_ids=capsule,laundry_windows=["周三晚：处理前半周内搭","周日：统一整理外层"],color_story=color_story)

def replan_dates(db:Session,user_id:str,plan_id:str,body:ReplanRequest)->WeeklyPlanResult:
    plan=db.get(WeeklyPlan,plan_id)
    if not plan or plan.user_id!=user_id:raise ValueError("plan not found")
    rows=list(db.scalars(select(PlanDay).where(PlanDay.plan_id==plan_id).order_by(PlanDay.date)));changed=set(body.changed_dates);days=[]
    for row in rows:
        if row.date in changed:
            day=body.updates[row.date];ids=_pick(db,user_id,day);ids=[x for x in ids if x not in body.unavailable_item_ids];row.item_ids=ids;row.occasion=day.occasion;row.weather=day.weather.model_dump();row.affected_by=list(changed);row.explanation={"reason":"只重排受变更影响的日期，其余计划保持不变。"}
        days.append(DayPlan(date=row.date,occasion=row.occasion,item_ids=row.item_ids,weather=row.weather,reason=row.explanation.get("reason","原计划保持不变")))
    plan.version+=1;db.commit();capsule=sorted({x for d in days for x in d.item_ids});return WeeklyPlanResult(plan_id=plan.id,version=plan.version,days=days,capsule_item_ids=capsule,laundry_windows=plan.summary.get("laundry_windows",[]),color_story=plan.summary.get("color_story",[]))

def create_travel_plan(db:Session,user_id:str,body:TravelPlanRequest)->TravelPlanResult:
    chosen=[];daily=[];usage={}
    for day in body.days:
        ids=_pick(db,user_id,day,locked=[chosen[0]] if chosen else [])
        if not ids:ids=_pick(db,user_id,day)
        for x in ids:
            if x not in chosen and len(chosen)<body.max_items:chosen.append(x)
            usage.setdefault(x,[]).append(day.date)
        daily.append(DayPlan(date=day.date,occasion=day.occasion,item_ids=ids,weather=day.weather,reason="以少量核心单品覆盖当天行程并保留天气备用。"))
    plan_id=f"travel_{uuid.uuid4().hex[:10]}";result=TravelPlanResult(plan_id=plan_id,destination=body.destination,packing_item_ids=chosen,daily_outfits=daily,reuse_map=usage,emergency_plan=["保留一件轻量防雨外层","极端降温时启用可叠穿内搭"],packing_order=["鞋履与重物","下装","上装卷叠","易皱外层置顶"],missing_items=[])
    db.add(TravelPlan(id=plan_id,user_id=user_id,destination=body.destination,start_date=body.start_date,end_date=body.end_date,constraints=body.model_dump(),result=result.model_dump()));db.commit();return result

def create_multiscene_plan(db:Session,user_id:str,body:MultiSceneRequest)->MultiSceneResult:
    first=body.scenes[0];base=_pick(db,user_id,type("Day",(),{"occasion":first.occasion,"formality_level":first.formality_level,"weather":body.weather})())
    transitions=[];carry=[];current=set(base)
    for scene in body.scenes[1:]:
        target=set(_pick(db,user_id,type("Day",(),{"occasion":scene.occasion,"formality_level":scene.formality_level,"weather":body.weather})(),locked=[x for x in base if x in current][:1]));remove=sorted(current-target);add=sorted(target-current);carry.extend(add);transitions.append({"scene":scene.name,"time":scene.time,"remove_item_ids":remove,"add_item_ids":add,"instruction":f"{scene.time} 前完成 {len(remove)+len(add)} 个最小调整"});current=target
    result=MultiSceneResult(plan_id=f"scene_{uuid.uuid4().hex[:10]}",base_item_ids=base,transitions=transitions,carry_item_ids=sorted(set(carry)),total_changes=sum(len(x["remove_item_ids"])+len(x["add_item_ids"]) for x in transitions),explanation="以全天基础穿搭为核心，只在正式度或活动强度变化时替换必要单品。")
    db.add(MultiScenePlan(id=result.plan_id,user_id=user_id,date=body.date,scenes=[x.model_dump() for x in body.scenes],base_item_ids=base,transitions=transitions,carry_item_ids=result.carry_item_ids));db.commit();return result
