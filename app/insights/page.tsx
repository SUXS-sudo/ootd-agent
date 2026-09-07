"use client";
import { AppImage } from "../components/AppImage";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import {
  apiRequest,
  fetchWardrobe,
  WardrobeItem,
  wardrobeImage,
} from "../lib/wardrobeApi";

type InsightsV2 = {
  most_worn_item_ids: string[];
  idle_item_ids: string[];
  core_item_ids: string[];
  isolated_item_ids: string[];
  functional_gaps: string[];
  color_distribution: Record<string, number>;
};
type ProductMetrics = { samples:number; funnel:{recommendation_batches:number;outfits_decided:number;adopted:number;rejected:number;replacement_actions:number;adoption_rate:number;rejection_rate:number;replacement_rate:number;rule_fallback_rate:number}; improvement:number };

type InsightItemListProps = {
  title: string;
  description: string;
  ids: string[];
  itemsById: Map<string, WardrobeItem>;
  tone?: "green" | "orange";
  emptyText: string;
};

function InsightItemList({ title, description, ids, itemsById, tone = "green", emptyText }: InsightItemListProps) {
  const items = ids.map(id => itemsById.get(id)).filter((item): item is WardrobeItem => Boolean(item));
  return <div className="card">
    <div className="toolbar" style={{ justifyContent: "space-between" }}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      <span className={`pill ${tone}`}>{items.length} 件</span>
    </div>
    <p className="subtle">{description}</p>
    {items.length ? items.map(item => <div className="item-row" key={item.id}>
      {wardrobeImage(item) && <AppImage className="wardrobe-thumb" src={wardrobeImage(item)} alt="" />}
      <div>
        <strong>{item.subcategory}</strong>
        <p className="subtle">{item.category} · 已穿 {item.wear_count} 次 · {item.clean_status}</p>
      </div>
    </div>) : <p className="subtle">{emptyText}</p>}
  </div>;
}

export default function Insights() {
  const [wardrobe, setWardrobe] = useState<WardrobeItem[]>([]);
  const [insights, setInsights] = useState<InsightsV2 | null>(null);
  const [metrics, setMetrics] = useState<ProductMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [items, advanced, productMetrics] = await Promise.all([
        fetchWardrobe(),
        apiRequest<InsightsV2>("/api/v1/wardrobe/insights-v2"),
        apiRequest<ProductMetrics>("/api/v1/personalization/metrics"),
      ]);
      setWardrobe(items);
      setInsights(advanced);
      setMetrics(productMetrics);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "衣橱洞察读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    Promise.all([
      fetchWardrobe(),
      apiRequest<InsightsV2>("/api/v1/wardrobe/insights-v2"),
      apiRequest<ProductMetrics>("/api/v1/personalization/metrics"),
    ]).then(([items, advanced, productMetrics]) => {
      setWardrobe(items);
      setInsights(advanced);
      setMetrics(productMetrics);
    }).catch(cause => {
      setError(cause instanceof Error ? cause.message : "衣橱洞察读取失败");
    }).finally(() => setLoading(false));
  }, []);

  const totalWearCount = wardrobe.reduce((total, item) => total + item.wear_count, 0);
  const itemsById = useMemo(() => new Map(wardrobe.map(item => [item.id, item])), [wardrobe]);
  const colors = Object.entries(insights?.color_distribution ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8);

  return <AppShell title="衣橱洞察">
    <div className="eyebrow">REAL DATA INSIGHTS</div>
    <h1 className="title">看清哪些衣服真正有用，哪些正在被闲置。</h1>
    <p className="subtle">数据来自当前数字衣橱、真实穿着次数和搭配图谱。衣橱发生变化后，可重新分析。</p>
    <button className="button button-primary" disabled={loading} onClick={load}>
      {loading ? "正在分析衣橱…" : "重新分析"}
    </button>
    {error && <p className="pill orange">{error}</p>}

    <div className="grid grid-3" style={{ marginTop: 24 }}>
      <div className="card"><div className="subtle">衣橱总量</div><div className="title">{wardrobe.length} 件</div></div>
      <div className="card"><div className="subtle">累计穿着次数</div><div className="title">{totalWearCount} 次</div></div>
      <div className="card"><div className="subtle">待盘活单品</div><div className="title">{insights?.idle_item_ids.length ?? 0} 件</div><p className="subtle">当前规则：穿着少于 4 次</p></div>
    </div>

    <section style={{ marginTop: 28 }}><div className="eyebrow">推荐是否越来越懂你</div><h2>推荐闭环</h2><p className="subtle">只统计你明确采用、拒绝或替换过的推荐；样本少时先展示事实，不做过度判断。</p><div className="grid grid-3"><div className="card"><div className="subtle">推荐采用率</div><div className="title">{metrics?.funnel.outfits_decided ? `${Math.round(metrics.funnel.adoption_rate * 100)}%` : "待积累"}</div><p className="subtle">{metrics?.funnel.adopted ?? 0} 次采用 / {metrics?.funnel.outfits_decided ?? 0} 次明确选择</p></div><div className="card"><div className="subtle">每批推荐替换率</div><div className="title">{metrics?.funnel.recommendation_batches ? `${Math.round(metrics.funnel.replacement_rate * 100)}%` : "待积累"}</div><p className="subtle">越低通常代表首轮推荐越接近你的需要</p></div><div className="card"><div className="subtle">规则回退率</div><div className="title">{metrics?.funnel.recommendation_batches ? `${Math.round(metrics.funnel.rule_fallback_rate * 100)}%` : "待积累"}</div><p className="subtle">模型不可用、快速模式或校验失败时会使用可靠规则</p></div></div></section>

    {insights && <>
      <div className="grid grid-2" style={{ marginTop: 18 }}>
        <InsightItemList
          title="核心单品"
          description="在搭配图谱中连接能力较强，适合围绕它们扩展组合。"
          ids={insights.core_item_ids}
          itemsById={itemsById}
          emptyText="暂未识别出核心单品。继续记录穿搭或补充衣橱资料后再分析。"
        />
        <InsightItemList
          title="高频单品"
          description="按真实穿着次数排序，反映你实际依赖的衣物。"
          ids={insights.most_worn_item_ids}
          itemsById={itemsById}
          emptyText="暂无穿着记录。采用今日 OOTD 后会开始累计。"
        />
        <InsightItemList
          title="待盘活单品"
          description="穿着次数少于 4 次，可以尝试重新搭配，也可以判断是否应继续保留。"
          ids={insights.idle_item_ids}
          itemsById={itemsById}
          tone="orange"
          emptyText="很好，目前没有明显低频单品。"
        />
        <InsightItemList
          title="搭配孤岛"
          description="与其他衣物连接较弱，不容易组成完整穿搭。"
          ids={insights.isolated_item_ids}
          itemsById={itemsById}
          tone="orange"
          emptyText="目前没有搭配孤岛，衣橱连接性不错。"
        />
      </div>

      <div className="grid grid-2" style={{ marginTop: 18 }}>
        <div className="card">
          <h3>颜色结构</h3>
          {colors.length ? colors.map(([name, count]) => <div key={name} style={{ margin: "18px 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}><span>{name}</span><b>{count} 件</b></div>
            <div className="progress"><span style={{ width: `${count / Math.max(1, wardrobe.length) * 100}%` }} /></div>
          </div>) : <p className="subtle">暂无颜色数据。</p>}
        </div>
        <div className="card">
          <h3>功能缺口</h3>
          <p className="subtle">根据已有单品的品类与天气能力，提示衣橱暂时覆盖不到的需求。这不是购买指令。</p>
          {insights.functional_gaps.length
            ? insights.functional_gaps.map(gap => <div className="item-row" key={gap}><span className="pill orange">缺口</span><strong>{gap}</strong></div>)
            : <p className="pill green">当前未发现明显功能缺口</p>}
        </div>
      </div>
    </>}
  </AppShell>;
}
