from types import SimpleNamespace
from app.ranking import filter_items,generate_candidates,deterministic_results,personalize_candidates,resolve_request_context
from app.schemas import OutfitRequest

def item(id,cat,sub,status="可穿",colors=None,formal=3,warm=2,constraints=None,wear=1,styles=None,fit="常规",length="常规"):
    return SimpleNamespace(id=id,category=cat,subcategory=sub,clean_status=status,colors=colors or ["白色"],formality_level=formal,warmth_level=warm,weather_constraints=constraints or [],wear_count=wear,styles=styles or [],fit=fit,length=length)
def inventory(): return [item("top1","上装","衬衫"),item("top2","上装","针织"),item("bottom1","下装","西裤"),item("bottom2","下装","直筒裤"),item("shoe1","鞋履","运动鞋"),item("shoe2","鞋履","乐福鞋"),item("outer1","外套","夹克")]
def test_unavailable_items_are_never_candidates():
    bad=item("bad","上装","衬衫",status="待洗");valid=filter_items(inventory()+[bad],OutfitRequest(),SimpleNamespace(avoided_colors=[]));assert bad not in valid
def test_locked_item_is_kept_and_results_only_use_real_ids():
    req=OutfitRequest(locked_item_ids=["bottom1"]);items=inventory();c=generate_candidates(filter_items(items,req,SimpleNamespace(avoided_colors=[])),req);assert c and all("bottom1" in {x.id for x in chosen} for _,chosen,_ in c);out=deterministic_results(c);allowed={x.id for x in items};assert all(set(o.item_ids)<=allowed for o in out)
def test_avoided_color_filtered():
    x=item("neon","上装","T恤",colors=["荧光绿"]);valid=filter_items(inventory()+[x],OutfitRequest(),SimpleNamespace(avoided_colors=["荧光绿"]));assert x not in valid
def test_rain_only_outerwear_is_hidden_on_dry_days_and_available_in_rain():
    raincoat=item("raincoat","外套","轻量防雨外套",constraints=["适合小雨","仅雨天推荐"])
    dry=OutfitRequest(weather={"rain_probability":.2})
    rainy=OutfitRequest(weather={"rain_probability":.6})
    profile=SimpleNamespace(avoided_colors=[])
    assert raincoat not in filter_items(inventory()+[raincoat],dry,profile)
    assert raincoat in filter_items(inventory()+[raincoat],rainy,profile)
def test_context_layer_uses_explicit_weather_and_activity_from_user_text():
    resolved=resolve_request_context(OutfitRequest(occasion="今天8度有小雨，还要步行45分钟"))
    assert resolved.weather.feels_like_c==8
    assert resolved.weather.rain_probability>=.65
    assert resolved.walking_minutes==45
def test_structure_layer_does_not_force_outerwear_on_warm_dry_days():
    req=OutfitRequest(weather={"feels_like_c":28,"temperature_c":28,"rain_probability":.1})
    candidates=generate_candidates(inventory(),req)
    assert candidates
    assert all(not any(x.category=="外套" for x in chosen) for _,chosen,_ in candidates)
def test_structure_layer_requires_available_outerwear_in_cold_weather():
    req=OutfitRequest(weather={"feels_like_c":8,"temperature_c":10,"rain_probability":.1})
    candidates=generate_candidates(inventory(),req)
    assert candidates
    assert all(any(x.category=="外套" for x in chosen) for _,chosen,_ in candidates)
def test_diversity_layer_changes_core_garments_not_only_shoes():
    candidates=generate_candidates(inventory(),OutfitRequest())[:3]
    core=[{x.id for x in chosen if x.category in {"上装","下装","连衣裙"}} for _,chosen,_ in candidates]
    assert len({frozenset(x) for x in core})==3
def test_explicit_skirt_request_is_a_hard_constraint():
    skirt=item("skirt1","下装","百褶半身裙")
    req=OutfitRequest(occasion="今天我想穿裙子",temporary_requirements=["今天我想穿裙子"])
    candidates=generate_candidates(inventory()+[skirt],req)
    assert candidates
    assert all(any("裙" in x.subcategory for x in chosen) for _,chosen,_ in candidates)
def test_negative_skirt_phrase_is_not_treated_as_required():
    req=OutfitRequest(occasion="今天不想穿裙子")
    assert generate_candidates(inventory(),req)
def test_dress_request_builds_complete_dress_outfits():
    dress=item("dress1","连衣裙","豆沙粉裹身连衣裙",colors=["豆沙粉"],formal=4,warm=1)
    req=OutfitRequest(occasion="周末约会，想穿连衣裙",temporary_requirements=["想穿连衣裙"])
    candidates=generate_candidates(inventory()+[dress],req)
    assert candidates
    assert all("dress1" in {x.id for x in chosen} for _,chosen,_ in candidates)
    assert all(not any(x.category in {"上装","下装"} for x in chosen) for _,chosen,_ in candidates)
def test_full_white_look_requires_every_core_garment_to_be_white_family():
    items=[item("white_top","上装","衬衫",colors=["白色"]),item("cream_bottom","下装","半身裙",colors=["米白"]),item("dark_bottom","下装","西裤",colors=["深灰"]),item("shoe","鞋履","运动鞋",colors=["白色"])]
    req=OutfitRequest(occasion="我今天想穿一身白色的衣服")
    candidates=generate_candidates(items,req)
    assert candidates
    assert all("dark_bottom" not in {x.id for x in chosen} for _,chosen,_ in candidates)
def test_full_white_look_returns_no_candidates_without_white_bottom():
    req=OutfitRequest(occasion="给我搭配全身白色")
    items=[item("white_top","上装","衬衫",colors=["白色"]),item("dark_bottom","下装","西裤",colors=["深灰"]),item("shoe","鞋履","运动鞋",colors=["白色"])]
    assert generate_candidates(items,req)==[]

def test_feedback_personalization_reranks_but_keeps_base_score_visible():
    candidates=generate_candidates(inventory(),OutfitRequest())
    target=next(row for row in reversed(candidates) if any(x.id=="top2" for x in row[1]))
    signals={"values":{"item:top2":1.0,"item:top1":-1.0},"strength":.35,"effective_samples":20}
    reranked=personalize_candidates(candidates,signals)
    assert any(x.id=="top2" for x in reranked[0][1])
    assert {"personalization","base_total"}<=reranked[0][2].keys()

def test_cold_start_does_not_change_ranking():
    candidates=generate_candidates(inventory(),OutfitRequest())
    assert personalize_candidates(candidates,{"values":{},"strength":0})==candidates
