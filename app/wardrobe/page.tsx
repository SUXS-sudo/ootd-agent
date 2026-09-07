"use client";
import { AppImage } from "../components/AppImage";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import { deleteWardrobeItem, fetchWardrobe, WardrobeItem, wardrobeFallback, wardrobeImage } from "../lib/wardrobeApi";

const WARDROBE_VIEW_KEY = "ootd.wardrobe-view";
type WardrobeView = { scrollY: number; query: string; category: string; status: string; restore: boolean; items?: WardrobeItem[] };

function readWardrobeView(): WardrobeView | null {
  try { return JSON.parse(sessionStorage.getItem(WARDROBE_VIEW_KEY) || "null") as WardrobeView | null; }
  catch { return null; }
}

export default function Wardrobe() {
  const [wardrobe, setWardrobe] = useState<WardrobeItem[]>([]), [query, setQuery] = useState(""), [category, setCategory] = useState("全部"), [status, setStatus] = useState("全部"), [message, setMessage] = useState("正在读取衣橱…"), [deleting, setDeleting] = useState<string | null>(null);
  useEffect(() => {
    const saved = readWardrobeView();
    if (saved?.restore && saved.items?.length) {
      Promise.resolve().then(() => { setQuery(saved.query); setCategory(saved.category); setStatus(saved.status); setWardrobe(saved.items || []); setMessage(""); });
      return;
    }
    fetchWardrobe().then(items => {
      if (saved?.restore) { setQuery(saved.query); setCategory(saved.category); setStatus(saved.status); }
      setWardrobe(items); setMessage("");
    }).catch(error => setMessage(error.message));
  }, []);
  useEffect(() => {
    if (!wardrobe.length) return;
    const saved = readWardrobeView();
    if (!saved?.restore) return;
    const frame = requestAnimationFrame(() => requestAnimationFrame(() => {
      window.scrollTo({ top: saved.scrollY, behavior: "instant" });
      sessionStorage.setItem(WARDROBE_VIEW_KEY, JSON.stringify({ ...saved, restore: false }));
    }));
    return () => cancelAnimationFrame(frame);
  }, [wardrobe]);
  const rememberView = () => {
    const saved={ scrollY: window.scrollY, query, category, status, restore: true, items: wardrobe } satisfies WardrobeView;
    sessionStorage.setItem(WARDROBE_VIEW_KEY, JSON.stringify(saved));
  };
  const removeItem=async(item:WardrobeItem)=>{if(!window.confirm(`确定从衣橱删除“${item.subcategory}”吗？此操作无法撤销。`))return;setDeleting(item.id);setMessage("");try{await deleteWardrobeItem(item.id);setWardrobe(current=>{const next=current.filter(value=>value.id!==item.id);sessionStorage.removeItem(WARDROBE_VIEW_KEY);return next});setMessage(`已删除“${item.subcategory}”`)}catch(error){setMessage(error instanceof Error?error.message:"删除失败")}finally{setDeleting(null)}};
  const statusGroup=(value:string)=>value==="可穿"?"可穿":["待洗","清洗中","晾晒中"].includes(value)?"待洗":"收纳";
  const categories = useMemo(() => [...new Set(wardrobe.map(item => item.category).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN")), [wardrobe]);
  const items = useMemo(() => wardrobe.filter(item => (!query || item.subcategory.includes(query) || item.colors.some(color => color.includes(query))) && (category === "全部" || item.category === category) && (status === "全部" || statusGroup(item.clean_status) === status)), [wardrobe, query, category, status]);
  const wearable = wardrobe.filter(item => item.clean_status === "可穿").length;
  const idle = wardrobe.filter(item => item.wear_count < 4).length;

  return <AppShell title="衣橱">
    <div className="section-head"><div><h1 className="title">我的衣橱</h1><p className="subtle">{wardrobe.length} 件衣物 · {wearable} 件现在可穿 · {idle} 件穿得较少</p></div><Link className="button button-primary" href="/wardrobe/upload">＋ 添加衣服</Link></div>
    {message && <div className="try-on-message">{message}</div>}
    <div className="toolbar" style={{ margin: "20px 0" }}><input className="filter" placeholder="搜索名称或颜色" value={query} onChange={event => setQuery(event.target.value)} /><select className="filter" value={category} onChange={event => setCategory(event.target.value)}><option value="全部">全部品类</option>{categories.map(value => <option key={value}>{value}</option>)}</select><select className="filter" value={status} onChange={event => setStatus(event.target.value)}><option>全部</option>{["可穿", "待洗", "收纳"].map(value => <option key={value}>{value}</option>)}</select></div>
    <div className="wardrobe-grid">{items.map(item => { const src = wardrobeImage(item), fallback = wardrobeFallback(item), available = item.clean_status === "可穿"; return <article className="card wardrobe-card" key={item.id}><Link href={`/wardrobe/${item.id}`} onClick={rememberView} className="wardrobe-card-link"><div className="wardrobe-photo">{src ? <AppImage src={src} alt={item.subcategory} onError={event => { if (fallback && event.currentTarget.src !== new URL(fallback, location.href).href) event.currentTarget.src = fallback; }} /> : <span>暂无图片</span>}<span className={`pill status ${available ? "green" : "orange"}`}>{item.clean_status}</span></div><div className="wardrobe-name">{item.subcategory}</div><div className="subtle">{item.category} · {item.colors.join("/")} · 穿过 {item.wear_count} 次</div></Link><button type="button" className="wardrobe-delete" disabled={deleting===item.id} onClick={()=>void removeItem(item)} aria-label={`删除${item.subcategory}`}>{deleting===item.id?"删除中":"删除"}</button></article>; })}</div>
    {!items.length && !message && <div className="card empty-state"><h2>没有找到衣物</h2><p className="subtle">换个筛选条件，或者添加一件新衣服。</p></div>}
  </AppShell>;
}
