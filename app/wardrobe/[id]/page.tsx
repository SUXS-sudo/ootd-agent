"use client";
import { AppImage } from "../../components/AppImage";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { fetchWardrobeItem, updateWardrobeItem, updateWardrobeStatus, WardrobeItem, WardrobeStatus, wardrobeImage } from "../../lib/wardrobeApi";

const statuses = ["可穿", "待洗", "清洗中", "晾晒中", "收纳中", "季节性收纳", "借出", "需要修补", "准备淘汰", "已淘汰"];
const BackToWardrobe = () => <Link className="button button-ghost" href="/wardrobe">← 返回衣橱</Link>;

export default function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [item, setItem] = useState<WardrobeItem | null>(null);
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState("正在读取单品…");

  useEffect(() => { fetchWardrobeItem(id).then(x => { setItem(x); setMessage(""); }).catch(e => setMessage(e.message)); }, [id]);

  async function save() {
    if (!item) return;
    try { setItem(await updateWardrobeItem(id, item)); setEditing(false); setMessage("信息已保存，推荐和换装会立即使用新数据"); }
    catch (e) { setMessage(e instanceof Error ? e.message : "保存失败"); }
  }

  async function changeStatus(value: WardrobeStatus) {
    if (!item) return;
    try {
      const result = await updateWardrobeStatus(id, value);
      setItem({ ...item, clean_status: value });
      setMessage(result.equivalent_replanned_dates.length ? `状态已更新，并重排 ${result.equivalent_replanned_dates.length} 天计划` : "状态已更新");
    } catch (e) { setMessage(e instanceof Error ? e.message : "状态更新失败"); }
  }

  if (!item) return <AppShell title="单品详情"><BackToWardrobe /><div className="try-on-message">{message}</div></AppShell>;

  return <AppShell title="单品详情">
    <div style={{ marginBottom: 18 }}><BackToWardrobe /></div>
    <div className="grid grid-2">
      <div className="card wardrobe-photo" style={{ minHeight: 520 }}>{wardrobeImage(item) ? <AppImage src={wardrobeImage(item)} alt={item.subcategory} /> : "暂无图片"}</div>
      <div>
        <div className="eyebrow">{item.id}</div>
        {editing ? <div className="form-grid">
          <div className="field"><label>名称</label><input className="input" value={item.subcategory} onChange={e => setItem({ ...item, subcategory: e.target.value })} /></div>
          <div className="field"><label>品类</label><select className="input" value={item.category} onChange={e => setItem({ ...item, category: e.target.value })}>{["上装", "下装", "连衣裙", "外套", "鞋履", "配饰", "包袋"].map(x => <option key={x}>{x}</option>)}</select></div>
          <div className="field"><label>颜色</label><input className="input" value={item.colors.join(",")} onChange={e => setItem({ ...item, colors: e.target.value.split(",").map(x => x.trim()).filter(Boolean) })} /></div>
          <div className="field"><label>版型</label><input className="input" value={item.fit} onChange={e => setItem({ ...item, fit: e.target.value })} /></div>
          <div className="field"><label>穿着层级</label><select className="input" value={item.wearing_layer || "主上装"} onChange={e => setItem({ ...item, wearing_layer: e.target.value as WardrobeItem["wearing_layer"] })}>{["内搭", "主上装", "外搭", "不可叠穿"].map(x => <option key={x}>{x}</option>)}</select></div>
          <button className="button button-primary" onClick={save}>保存修改</button><button className="button button-ghost" onClick={() => setEditing(false)}>取消</button>
        </div> : <>
          <h1 className="title">{item.subcategory}</h1>
          <div className="toolbar"><span className={item.clean_status === "可穿" ? "pill green" : "pill orange"}>{item.clean_status}</span><span className="pill">{item.category}</span><span className="pill">{item.colors.join("/")}</span></div>
          <div className="card" style={{ marginTop: 22 }}>
            <div className="item-row"><b>当前状态</b><span className="spacer" /><select className="filter" value={item.clean_status} onChange={e => changeStatus(e.target.value as WardrobeStatus)}>{statuses.map(x => <option key={x}>{x}</option>)}</select></div>
            <div className="item-row"><b>穿着次数</b><span className="spacer" />{item.wear_count} 次</div>
            <div className="item-row"><b>穿着层级</b><span className="spacer" />{item.wearing_layer || "主上装"}</div>
            <div className="item-row"><b>保暖等级</b><span className="spacer" />{item.warmth_level} / 5</div>
            <div className="item-row"><b>正式程度</b><span className="spacer" />{item.formality_level} / 5</div>
            <div className="item-row"><b>适用季节</b><span className="spacer" />{item.seasons.join(" · ") || "未设置"}</div>
          </div>
          <div className="toolbar" style={{ marginTop: 18 }}><button className="button button-primary" onClick={() => setEditing(true)}>编辑信息</button></div>
        </>}
        {message && <div className="try-on-message">{message}</div>}
      </div>
    </div>
  </AppShell>;
}
