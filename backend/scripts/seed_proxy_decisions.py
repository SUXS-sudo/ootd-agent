"""Create honest expert-proxy labels through the real recommendation API."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal
from app.models import CandidateImpression,DecisionOutcome,Outfit

SCENARIOS=[
    ("日常通勤，步行45分钟",18,.15,45,3),("重要客户会议",20,.1,20,5),("周末咖啡约会",23,.1,30,2),("雨天通勤，不穿高跟鞋",17,.8,40,3),
    ("夏季办公室，空调较冷",31,.2,20,3),("朋友聚餐，想有一点风格",24,.2,25,2),("机场出行，要久坐和走路",22,.2,70,2),("正式面试",16,.2,25,5),
    ("周末逛街，走路很多",27,.15,90,2),("晚间约会，不要太正式",21,.1,25,3),("小雨天休闲出门",25,.65,35,2),("降温后的日常通勤",9,.2,30,3),
    ("商务休闲午餐",19,.1,20,4),("看展，想穿得有辨识度",22,.1,50,2),("普通工作日，舒适优先",26,.1,45,3),("婚礼宾客，得体但不抢眼",20,.15,30,5),
    ("短途旅行第一天",28,.2,80,2),("周末家庭聚会",18,.1,20,3),("大风降温通勤",7,.1,35,3),("晴天城市散步",25,.05,100,2),
    ("晚间正式晚餐",15,.1,20,5),("居家附近办事",29,.1,30,1),("雨后约会，鞋子耐走",20,.55,55,3),("创意行业工作日",23,.15,35,3),
]

def proxy_score(outfit,walking,formality,rain):
    scores=outfit.get("scores",{});value=.27*scores.get("weather",0)+.22*scores.get("occasion",0)+.18*scores.get("preference",0)+.14*scores.get("color",0)+.1*scores.get("proportion",0)+.05*scores.get("freshness",0)+.04*scores.get("utilization",0)
    if walking>=45:value+=.05*scores.get("preference",0)
    if formality>=4:value+=.05*scores.get("occasion",0)
    if rain>=.5:value+=.05*scores.get("weather",0)
    return value

def main():
    created=0;headers={}
    with TestClient(app) as client:
        for index,(occasion,temp,rain,walking,formality) in enumerate(SCENARIOS):
            response=client.post("/api/v1/outfits/generate",headers=headers,json={"occasion":occasion,"formality_level":formality,"walking_minutes":walking,"mode":"fast","weather":{"city":"代理评测城市","temperature_c":temp,"feels_like_c":temp,"rain_probability":rain,"wind_level":3,"condition":"雨" if rain>=.5 else "多云"}})
            if response.status_code!=200:print(f"SKIP {index+1}: {response.status_code} {response.text[:120]}");continue
            outfits=response.json()["outfits"];winner=max(outfits,key=lambda row:proxy_score(row,walking,formality,rain))
            with SessionLocal() as db:
                outfit=db.get(Outfit,winner["outfit_id"]);impression_id=(outfit.result or {}).get("impression_id");impression=db.get(CandidateImpression,impression_id)
                if impression and not db.scalar(select(DecisionOutcome).where(DecisionOutcome.impression_id==impression.id)):
                    db.add(DecisionOutcome(decision_id=impression.decision_id,impression_id=impression.id,outfit_id=outfit.id,reward=.35,adopted=False,source="expert_proxy",replaced_item_ids=[],feedback_delay_seconds=0));db.commit();created+=1
            print(f"{index+1:02d} {occasion}: {winner['title']}")
    print(f"created_proxy_decisions={created} requested={len(SCENARIOS)}")

if __name__=="__main__":main()
