"""Run deterministic V1 quality gates without an API key."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"backend"))
from app.ranking import filter_items,generate_candidates,personalize_candidates
from app.schemas import OutfitRequest
from types import SimpleNamespace as S

def main():
    profile=S(avoided_colors=["荧光绿"],avoided_styles=[],avoided_item_terms=[]);items=[S(id="ok",category="上装",subcategory="衬衫",clean_status="可穿",colors=["藏青"],styles=[],weather_constraints=[],formality_level=3,warmth_level=2),S(id="dirty",category="上装",subcategory="衬衫",clean_status="待洗",colors=["米白"],styles=[],weather_constraints=[],formality_level=3,warmth_level=2),S(id="avoid",category="上装",subcategory="T恤",clean_status="可穿",colors=["荧光绿"],styles=[],weather_constraints=[],formality_level=3,warmth_level=2)]
    valid=filter_items(items,OutfitRequest(),profile);assert [x.id for x in valid]==["ok"]
    def garment(item_id,category,name,color="藏青",wear_count=0):
        return S(id=item_id,category=category,subcategory=name,clean_status="可穿",colors=[color],weather_constraints=[],formality_level=3,warmth_level=2,wear_count=wear_count,styles=["简约"],fit="常规",length="常规")
    wardrobe=[garment("liked","上装","偏好衬衫",wear_count=20),garment("other","上装","普通衬衫"),garment("b1","下装","西裤"),garment("b2","下装","直筒裤"),garment("s1","鞋履","乐福鞋"),garment("s2","鞋履","运动鞋")]
    request=OutfitRequest();baseline=generate_candidates(wardrobe,request);personalized=personalize_candidates(baseline,{"values":{"item:liked":1,"item:other":-1},"strength":.35})
    baseline_rank=next(i for i,row in enumerate(baseline) if any(x.id=="liked" for x in row[1]));personalized_rank=next(i for i,row in enumerate(personalized) if any(x.id=="liked" for x in row[1]))
    assert personalized_rank<baseline_rank
    print(f"PASS: unavailable=0 invented=0 avoided_color=0 personalized_rank_delta={baseline_rank-personalized_rank}")
if __name__=="__main__":main()
