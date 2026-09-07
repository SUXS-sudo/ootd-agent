from itertools import combinations
from sqlalchemy import delete,select
from sqlalchemy.orm import Session
from .models import WardrobeItem,WardrobeRelation,Outfit,OutfitFeedback
from .schemas import WardrobeGraphResult,GraphNode,GraphEdge

def rebuild_graph(db:Session,user_id:str)->WardrobeGraphResult:
    items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id==user_id)));outfits=list(db.scalars(select(Outfit).where(Outfit.user_id==user_id)))
    adopted={f.outfit_id for f in db.scalars(select(OutfitFeedback).where(OutfitFeedback.adopted==True))};counts={};reasons={}
    for o in outfits:
        boost=1.5 if o.id in adopted else 1
        for a,b in combinations(sorted(o.item_ids),2): counts[(a,b)]=counts.get((a,b),0)+boost;reasons[(a,b)]=["历史有效组合"]+(["用户实际采用"] if o.id in adopted else [])
    by_id={x.id:x for x in items}
    for a,b in combinations(items,2):
        if a.category==b.category: continue
        key=tuple(sorted((a.id,b.id)));color_bonus=.35 if set(a.colors).isdisjoint(b.colors) else .2;style_bonus=.25 if set(a.styles)&set(b.styles) else .1
        counts[key]=counts.get(key,0)+color_bonus+style_bonus;reasons.setdefault(key,["品类互补","配色与风格兼容"])
    max_score=max(counts.values(),default=1);edges=[];degree={x.id:0.0 for x in items};db.execute(delete(WardrobeRelation).where(WardrobeRelation.user_id==user_id))
    for (a,b),raw in counts.items():
        if a not in by_id or b not in by_id:continue
        score=round(raw/max_score,3);degree[a]+=score;degree[b]+=score
        if score>=.2:
            db.add(WardrobeRelation(user_id=user_id,source_item_id=a,target_item_id=b,score=score,evidence={"reasons":list(dict.fromkeys(reasons[(a,b)]))}));edges.append(GraphEdge(source=a,target=b,score=score,reasons=list(dict.fromkeys(reasons[(a,b)]))))
    ranked=sorted(degree,key=degree.get,reverse=True);core=ranked[:max(1,min(5,len(ranked)))];isolated=[i for i,v in degree.items() if v<.35]
    max_degree=max(degree.values(),default=1) or 1
    nodes=[GraphNode(item_id=x.id,label=x.subcategory,category=x.category,core_score=round(degree[x.id]/max_degree,3),isolated=x.id in isolated) for x in items];db.commit();return WardrobeGraphResult(nodes=nodes,edges=edges,isolated_item_ids=isolated,core_item_ids=core)
