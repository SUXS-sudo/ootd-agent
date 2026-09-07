export type WardrobeItem = { id: string; name: string; category: string; occasion: string; color: string; season: string; status: string; wear: number; image: string; emoji: string; meta: string };

const wardrobeRows: [string,string,string,string,string,string,string,number,string][] = [
  ["item_7010", "炭灰休闲西装", "外套", "通勤", "炭灰", "四季", "可穿", 1, "/clothes/item_7010-charcoal-blazer.png"],
  ["item_7020", "雾蓝宽松卫衣", "上装", "休闲", "雾蓝", "春秋", "可穿", 2, "/clothes/item_7020-blue-hoodie.png"],
  ["item_7030", "白色亚麻短袖衬衫", "上装", "夏季", "白色", "夏季", "可穿", 1, "/clothes/item_7030-white-linen-shirt.png"],
  ["item_7040", "酒红缎面半裙", "下装", "约会", "酒红", "四季", "可穿", 1, "/clothes/item_7040-burgundy-skirt.png"],
  ["item_7050", "黑色直筒牛仔裤", "下装", "日常", "黑色", "四季", "可穿", 3, "/clothes/item_7050-black-jeans.png"],
  ["item_7060", "奶油色帆布鞋", "鞋履", "休闲", "奶油色", "四季", "可穿", 2, "/clothes/item_7060-cream-sneakers.png"],
  ["item_7070", "焦糖色皮革肩包", "配饰", "通勤", "焦糖色", "四季", "可穿", 1, "/clothes/item_7070-caramel-bag.png"],
  ["item_7080", "深绿色轻量雨衣", "外套", "雨天", "深绿", "春夏秋", "可穿", 1, "/clothes/item_7080-green-rain-jacket.png"],
  ["item_7090", "酒红色玛丽珍平底鞋", "鞋履", "约会", "酒红", "四季", "可穿", 0, "/clothes/item_7090-burgundy-mary-jane.png"],
  ["item_7100", "杏仁米色低跟露跟鞋", "鞋履", "通勤", "杏仁米", "春夏秋", "可穿", 0, "/clothes/item_7100-beige-slingback.png"],
  ["item_6010", "驼色羊毛大衣", "外套", "通勤", "驼色", "秋冬", "可穿", 3, "/clothes/item_6010-camel-coat.png"],
  ["item_6020", "浅粉宽松衬衫", "上装", "通勤", "浅粉", "春夏", "可穿", 4, "/clothes/item_6020-pink-blouse.png"],
  ["item_6030", "森林绿百褶半裙", "下装", "约会", "森林绿", "秋冬", "可穿", 5, "/clothes/item_6030-forest-skirt.png"],
  ["item_6040", "黑色短靴", "鞋履", "秋冬", "黑色", "秋冬", "可穿", 6, "/clothes/item_6040-black-boots.png"],
  ["item_6050", "酒红针织开衫", "上装", "通勤", "酒红", "秋冬", "可穿", 2, "/clothes/item_6050-burgundy-cardigan.png"],
  ["item_6060", "海军蓝阔腿裤", "下装", "通勤", "海军蓝", "四季", "可穿", 4, "/clothes/item_6060-navy-trousers.png"],
  ["item_2088", "藏青短款夹克", "外套", "通勤", "藏青", "春秋", "可穿", 12, "/clothes/item_2088-navy-jacket.png"],
  ["item_1802", "米白针织上衣", "上装", "简约", "米白", "秋冬", "可穿", 18, "/clothes/item_1802-cream-knit.png"],
  ["item_2204", "雾蓝棉质衬衫", "上装", "通勤", "雾蓝", "春夏秋", "可穿", 8, "/clothes/item_2204-misty-blue-shirt.png"],
  ["item_3301", "高腰直筒西裤", "下装", "利落", "深灰", "四季", "可穿", 14, "/clothes/item_3301-dark-gray-trousers.png"],
  ["item_3310", "浅卡其阔腿裤", "下装", "松弛", "卡其", "春夏", "可穿", 7, "/clothes/item_3310-khaki-trousers.png"],
  ["item_4011", "白色轻量运动鞋", "鞋履", "舒适", "白色", "四季", "可穿", 21, "/clothes/item_4011-white-sneakers.png"],
  ["item_4018", "棕色乐福鞋", "鞋履", "轻正式", "棕色", "四季", "可穿", 9, "/clothes/item_4018-brown-loafers.png"],
  ["item_5012", "焦糖色托特包", "包袋", "通勤", "焦糖色", "四季", "待清洁", 11, ""],
];
export const wardrobe: WardrobeItem[] = wardrobeRows.map(([id,name,category,occasion,color,season,status,wear,image]) => ({id,name,category,occasion,color,season,status,wear,image,emoji:"",meta:`${category} · ${occasion}`}));

export const wardrobeImages = Object.fromEntries(wardrobe.map(item => [item.id, item.image]));

export const outfits = [
  { kind:"真实衣橱推荐", title: "藏青夹克 × 米白针织 × 直筒西裤", desc: "使用你衣橱中已有的三件高频单品，适合通勤和空调房。", items: ["item_2088", "item_1802", "item_3301", "item_4011"], scores:["舒适 94","场合 92","复用 90"] },
  { kind:"轻松日常", title: "雾蓝衬衫 × 浅卡其阔腿裤", desc: "清爽、轻松，适合周末散步或日常出行。", items: ["item_2204", "item_3310", "item_4018"], scores:["配色 93","风格 90","舒适 88"] },
];
