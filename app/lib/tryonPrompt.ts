import { WardrobeItem } from "./wardrobeApi";

const LAYER_ORDER = { "内搭": 1, "主上装": 2, "外搭": 3, "不可叠穿": 2 } as const;
const SAME_LAYER_ORDER = [/打底|吊带|背心/, /衬衫|T恤/, /针织背心|马甲/, /针织|毛衣|卫衣/];

export function wardrobeLayer(item: WardrobeItem) {
  if (item.wearing_layer) return item.wearing_layer;
  if (item.category === "外套" || /开衫|夹克|西装|风衣|大衣|马甲/.test(item.subcategory)) return "外搭";
  if (/打底|吊带|背心|内衣/.test(item.subcategory)) return "内搭";
  return "主上装";
}

export function buildOutfitTryOnPrompt(itemIds: string[], wardrobe: WardrobeItem[]) {
  const items = itemIds.map(id => wardrobe.find(item => item.id === id)).filter(Boolean);
  const list = items.map((item, index) => `${index + 1}. ${item!.category}：${item!.subcategory}（${item!.colors.join("/")}；穿着层级：${wardrobeLayer(item!)}）`).join("\n");
  const upperItems = items.filter(item => item!.category === "上装" || item!.category === "外套");
  const sameLayerRank = (item: WardrobeItem) => {
    const rank = SAME_LAYER_ORDER.findIndex(pattern => pattern.test(item.subcategory));
    return rank < 0 ? SAME_LAYER_ORDER.length : rank;
  };
  const orderedLayers = [...upperItems].sort((a, b) => LAYER_ORDER[wardrobeLayer(a!)] - LAYER_ORDER[wardrobeLayer(b!)] || sameLayerRank(a!) - sameLayerRank(b!));
  const hasExclusiveTop = upperItems.some(item => wardrobeLayer(item!) === "不可叠穿");
  if (hasExclusiveTop && upperItems.length > 1) {
    const exclusiveNames = upperItems.filter(item => wardrobeLayer(item!) === "不可叠穿").map(item => item!.subcategory).join("、");
    throw new Error(`${exclusiveNames}已标记为不可叠穿，请取消其他上装或修改该单品的穿着层级`);
  }
  const ambiguousMainTops = upperItems.filter(item => wardrobeLayer(item!) === "主上装");
  if (ambiguousMainTops.length > 1 && new Set(ambiguousMainTops.map(item => sameLayerRank(item!))).size !== ambiguousMainTops.length) {
    throw new Error(`${ambiguousMainTops.map(item => item!.subcategory).join("、")}都是主上装且无法可靠判断内外，请在数字衣橱中把其中一件改为内搭或外搭`);
  }
  const layering = upperItems.length > 1
    ? `严格按由内到外的顺序穿着：${orderedLayers.map(item => `${item!.subcategory}（${wardrobeLayer(item!)}）`).join(" → ")}。不得自行颠倒层级。`
    : "按单品标注的穿着层级呈现，不要擅自增加额外内搭或外搭。";
  const hasShoes = items.some(item => item!.category === "鞋履");
  const hasBag = items.some(item => item!.category === "包袋" || item!.category === "配饰" && item!.subcategory.includes("包"));
  return `你是专业虚拟试衣图片编辑器。第一张图是人物，第二张图是带编号和类别标签的完整穿搭参考图。
必须把下列每一件已选单品都应用到同一位人物身上，不得漏掉任何一件：
${list}
保持人物的脸部身份、发型、身体比例、整体姿态、相机角度和背景一致；准确保留每件单品的颜色、图案、结构和材质特征。
${layering}
${hasShoes ? "鞋履是必选单品：必须替换人物原来的鞋，左右脚穿同一双所选鞋；画面必须从头到脚完整构图，清楚露出双脚和鞋底接触地面的位置，不得裁掉脚部。" : ""}
${hasBag ? "包袋是必选单品：必须让人物自然肩背、斜挎或手提参考包；允许为持包对手臂和手部姿势做最小必要调整，不得以保持原姿势为由省略包。" : ""}
输出一张写实自然的单人全身换装照片。不要文字、编号、拼图、水印、额外衣物或前后对比排版。`;
}
