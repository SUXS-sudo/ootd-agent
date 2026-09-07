from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import User,UserProfile,WardrobeItem,Outfit

LEGACY_DEMO_PREFERENCES={
    "height_cm":168,
    "temperature_preference":"怕冷",
    "preferred_styles":["简约","通勤","轻复古"],
    "preferred_colors":["藏青","米白","棕色"],
    "avoided_colors":["荧光绿"],
    "restrictions":["不穿高跟鞋"],
    "visual_goals":["提升腰线","整体利落"],
}

def seed_demo(db:Session):
    if not db.get(User,"u_1001"):
        db.add(User(id="u_1001",email="demo@yixu.local")); db.add(UserProfile(user_id="u_1001"))
        demo_profile=None
    else:
        demo_profile=db.get(UserProfile,"u_1001")
        if demo_profile is None:
            db.add(UserProfile(user_id="u_1001"))
    # One-time compatibility cleanup: only remove the exact old preset. This
    # keeps preferences that someone intentionally entered while using demo mode.
    if demo_profile and all(getattr(demo_profile,key)==value for key,value in LEGACY_DEMO_PREFERENCES.items()):
        demo_profile.height_cm=None
        demo_profile.temperature_preference=""
        demo_profile.preferred_styles=[]
        demo_profile.avoided_styles=[]
        demo_profile.preferred_item_terms=[]
        demo_profile.avoided_item_terms=[]
        demo_profile.preferred_colors=[]
        demo_profile.avoided_colors=[]
        demo_profile.restrictions=[]
        demo_profile.visual_goals=[]
        demo_profile.photo_retention_consent=False
    rows=[
      ("item_2088","外套","短款夹克",["藏青"],2,3,["简约","通勤"],12,["不适合大雨"]),("item_1802","上装","针织上衣",["米白"],2,3,["简约"],18,[]),("item_2204","上装","棉质衬衫",["雾蓝"],1,4,["通勤"],8,[]),("item_3301","下装","直筒西裤",["深灰"],2,4,["通勤"],14,[]),("item_3310","下装","阔腿裤",["浅卡其"],1,3,["松弛"],7,[]),("item_6030","下装","森林绿百褶半身裙",["森林绿"],2,3,["轻复古","约会"],5,[]),("item_7040","下装","酒红缎面半身裙",["酒红"],1,3,["优雅","约会"],1,[]),("item_6040","鞋履","黑色短靴",["黑色"],3,3,["利落","秋冬"],6,[]),("item_7060","鞋履","奶油色帆布鞋",["奶油色"],1,2,["休闲","简约"],2,[]),("item_7090","鞋履","酒红色玛丽珍平底鞋",["酒红"],1,3,["优雅","轻复古"],0,[]),("item_7100","鞋履","杏仁米色低跟露跟鞋",["杏仁米"],1,4,["通勤","优雅"],0,["不适合雨天"]),("item_4011","鞋履","运动鞋",["白色"],1,2,["运动","简约"],21,[]),("item_4018","鞋履","乐福鞋",["棕色"],1,4,["轻复古","通勤"],9,[]),("item_5012","包袋","托特包",["焦糖"],1,3,["通勤"],11,[]),
      ("item_8201","外套","黑色修身西装",["黑色"],2,5,["通勤","正式","利落"],1,[]),("item_8202","连衣裙","豆沙粉裹身连衣裙",["豆沙粉"],1,4,["优雅","约会","正式"],0,["不适合雨天"]),("item_8203","外套","橄榄绿轻量防雨外套",["橄榄绿"],2,2,["户外","休闲","机能"],0,["适合小雨","仅雨天推荐"]),("item_8204","下装","深靛蓝直筒牛仔裤",["深靛蓝"],2,2,["休闲","简约","街头"],3,[]),
      ("item_8301","上装","白色亚麻翻领短袖衬衫",["白色"],1,3,["简约","通勤","度假"],0,[]),("item_8302","上装","豆沙粉真丝飘带领衬衫",["豆沙粉"],1,4,["优雅","通勤","正式"],0,["不适合大雨"]),("item_8303","上装","黑色修身高领打底衫",["黑色"],3,3,["简约","通勤","利落"],0,[]),("item_8304","上装","焦糖色方领灯笼袖上衣",["焦糖"],1,3,["复古","约会","通勤"],0,[]),("item_8305","上装","森林绿亨利领针织上衣",["森林绿"],2,2,["休闲","轻复古"],0,[]),("item_8306","上装","天蓝色牛津纺衬衫",["天蓝"],2,4,["通勤","简约","正式"],0,[]),("item_8307","上装","米白色罗纹圆领短款针织衫",["米白"],2,3,["简约","温柔","通勤"],0,[]),("item_8308","上装","浅灰色落肩纯棉卫衣",["浅灰"],2,1,["休闲","运动"],0,[]),("item_8309","上装","奶油黄圆领羊毛套头衫",["奶油黄"],4,2,["温柔","休闲"],0,[]),
      ("item_8310","下装","藏青直筒西裤",["藏青"],2,4,["通勤","正式","利落"],0,[]),("item_8311","下装","黑色直筒牛仔裤",["黑色"],2,2,["休闲","简约"],0,[]),
      ("item_8312","外套","炭灰通勤西装",["炭灰"],2,4,["商务","通勤","正式"],0,[]),("item_8313","外套","驼色长款羊毛大衣",["驼色"],4,4,["经典","通勤","正式"],0,["不适合大雨"]),("item_8314","外套","绿色轻量防雨夹克",["绿色"],2,2,["户外","休闲","机能"],0,["耐雨","防水","仅雨天推荐"]),
      ("item_8316","鞋履","米白芭蕾平底鞋",["米白"],1,3,["温柔","通勤","舒适"],0,["不适合大雨"])]
    image_urls={"item_2088":"/clothes/藏青短款夹克.png","item_1802":"/clothes/米白针织上衣.png","item_2204":"/clothes/雾霾蓝棉质衬衫.png","item_3301":"/clothes/深灰直筒西裤.png","item_3310":"/clothes/卡其阔腿裤.png","item_6030":"/clothes/森林绿半身裙.png","item_7040":"/clothes/酒红缎面半身裙.png","item_6040":"/clothes/黑色短靴.png","item_7060":"/clothes/奶油色帆布鞋.png","item_7090":"/clothes/酒红玛丽珍鞋.png","item_7100":"/clothes/杏仁米色低跟鞋.png","item_4011":"/clothes/白色运动鞋.png","item_4018":"/clothes/棕色乐福鞋.png","item_5012":"/clothes/焦糖色托特包.png","item_8201":"/clothes/黑色修身西装.png","item_8202":"/clothes/豆沙粉裹身连衣裙.png","item_8203":"/clothes/橄榄绿轻量雨衣.png","item_8204":"/clothes/深靛蓝直筒牛仔裤.png",
      "item_8301":"/clothes/白色亚麻翻领短袖衬衫.png","item_8302":"/clothes/豆沙粉真丝飘带领衬衫.png","item_8303":"/clothes/黑色修身高领打底衫.png","item_8304":"/clothes/焦糖色方领灯笼袖上衣.png","item_8305":"/clothes/森林绿亨利领针织上衣.png","item_8306":"/clothes/天蓝色牛津纺衬衫.png","item_8307":"/clothes/米白色罗纹圆领短款针织衫.png","item_8308":"/clothes/浅灰色落肩纯棉卫衣.png","item_8309":"/clothes/奶油黄圆领羊毛套头衫.png","item_8310":"/clothes/藏青西裤.png","item_8311":"/clothes/黑色牛仔裤.png","item_8312":"/clothes/炭灰西装.png","item_8313":"/clothes/驼色长款大衣.png","item_8314":"/clothes/绿色防雨外套.png","item_8316":"/clothes/米白芭蕾平底鞋.png"}
    for id,cat,sub,colors,warm,formal,styles,_legacy_wear,constraints in rows:
        row=db.get(WardrobeItem,id)
        duplicate=db.scalar(select(WardrobeItem).where(WardrobeItem.user_id=="u_1001",(WardrobeItem.subcategory==sub)|(WardrobeItem.image_url==image_urls.get(id)))) if not row else None
        if not row and not duplicate: db.add(WardrobeItem(id=id,user_id="u_1001",category=cat,subcategory=sub,colors=colors,material_guess=[],material_confidence=.8,pattern="纯色",fit="常规",length="常规",warmth_level=warm,formality_level=formal,styles=styles,seasons=["春","秋"],weather_constraints=constraints,clean_status="可穿",wear_count=0,last_worn_at=None,image_url=image_urls.get(id)))
        elif row and not row.image_url and image_urls.get(id): row.image_url=image_urls[id]
    # Repair legacy/demo rows whose uploaded test asset was removed. All consumers
    # then receive a usable image through the same wardrobe API record.
    generated=Path(__file__).resolve().parents[1]/"generated"
    wardrobe_items=list(db.scalars(select(WardrobeItem).where(WardrobeItem.user_id=="u_1001")))
    ivory_flats=next((item for item in wardrobe_items if item.subcategory=="米白平底鞋"),None)
    for item in wardrobe_items:
        name=item.subcategory or ""
        # Remove a legacy development fixture that was accidentally stored in the
        # demo wardrobe. The canonical "米白平底鞋" record is kept.
        if name.startswith("测试米白平底鞋"):
            if ivory_flats:
                for outfit in db.scalars(select(Outfit).where(Outfit.user_id=="u_1001")):
                    if item.id in outfit.item_ids:
                        outfit.item_ids=[ivory_flats.id if value==item.id else value for value in outfit.item_ids]
            db.delete(item)
            continue
        broken_generated=bool(item.image_url and item.image_url.startswith("/generated/") and not (generated/item.image_url.rsplit("/",1)[-1]).exists())
        if broken_generated:
            item.image_url=None
    db.commit()
    from .preference_cache import invalidate_preferences
    invalidate_preferences("u_1001")
