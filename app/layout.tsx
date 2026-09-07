import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const protocol = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const base = new URL(`${protocol}://${host}`);
  return { title:"衣序 · 主动个人形象 Agent", description:"从每日 OOTD、一周计划到重要时刻主动准备，基于真实衣橱持续学习你的个人风格。", icons:{icon:"/favicon.svg"}, metadataBase:base, openGraph:{title:"衣序 · 越来越懂你，重要时刻提前准备。",description:"每日穿搭 · 一周计划 · 主动形象 Agent",images:[{url:"/og-v3.png",width:1732,height:908}]}, twitter:{card:"summary_large_image",title:"衣序 · 越来越懂你，重要时刻提前准备。",description:"每日穿搭 · 一周计划 · 主动形象 Agent",images:["/og-v3.png"]} };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
