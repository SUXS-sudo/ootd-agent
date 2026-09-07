"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { API_URL } from "../lib/wardrobeApi";

const items = [["/today", "今天"], ["/wardrobe", "衣橱"], ["/week-plan", "计划"], ["/settings/privacy", "我的"]] as const;
const NAV_SCROLL_KEY = "yixu.sidebar.scrollTop";

export function AppShell({ children, title = "衣序" }: { children: React.ReactNode; title?: string }) {
  const path = usePathname();
  const navRef = useRef<HTMLElement>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/api/v1/health`).then(response => active && setOnline(response.ok)).catch(() => active && setOnline(false));
    return () => { active = false; };
  }, []);

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const saved = Number(sessionStorage.getItem(NAV_SCROLL_KEY) || 0);
    nav.scrollTop = saved;
  }, [path]);

  const rememberNavPosition = () => {
    if (navRef.current) sessionStorage.setItem(NAV_SCROLL_KEY, String(navRef.current.scrollTop));
  };

  return <div className="app-shell">
    <aside className="sidebar">
      <Link href="/today" className="brand"><span className="brand-mark">衣</span>衣序</Link>
      <nav className="nav" ref={navRef} onScroll={rememberNavPosition}>
        {items.map(([href, label]) => <Link key={href} href={href} onClick={rememberNavPosition} className={path.startsWith(href) ? "active" : ""}>{label}</Link>)}
      </nav>
      <div className="side-foot">让每一件衣服，都有被穿上的理由。</div>
    </aside>
    <main className="main">
      <header className="topbar"><b>{title}</b><div className="top-actions">{online === false && <span className="pill orange">服务未连接</span>}<div className="avatar">我</div></div></header>
      <div className="content">{children}</div>
    </main>
    <nav className="mobile-nav">{items.map(([href, label]) => <Link key={href} href={href}>{label}</Link>)}</nav>
  </div>;
}
