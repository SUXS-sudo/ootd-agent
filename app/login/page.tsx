"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { localAuth } from "../lib/wardrobeApi";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true); setError("");
    try { await localAuth(mode, email, password); router.replace(mode === "register" ? "/onboarding" : "/today"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "登录失败"); }
    finally { setBusy(false); }
  }

  return <main style={{minHeight:"100vh",display:"grid",placeItems:"center",padding:20}}>
    <div className="card" style={{width:"min(430px,100%)",padding:34}}>
      <div className="brand"><span className="brand-mark">衣</span>衣序</div>
      <h1 className="title">{mode === "login" ? "欢迎回来" : "创建本地账号"}</h1>
      <p className="subtle">账号、密码和衣橱数据只保存在你自己的服务中，不依赖第三方登录。</p>
      <div className="form-grid">
        <div className="field"><label>邮箱</label><input className="input" type="email" autoComplete="email" value={email} onChange={event=>setEmail(event.target.value)} /></div>
        <div className="field"><label>密码</label><input className="input" type="password" minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={event=>setPassword(event.target.value)} /></div>
        <button className="button button-primary" disabled={busy||!email||password.length<8} onClick={submit}>{busy?"处理中…":mode === "login"?"登录":"注册并登录"}</button>
      </div>
      {error&&<p className="pill orange">{error}</p>}
      <button className="button button-ghost" style={{width:"100%",marginTop:10}} onClick={()=>{setMode(mode === "login"?"register":"login");setError("")}}>{mode === "login"?"没有账号？本地注册":"已有账号？返回登录"}</button>
      <p className="subtle" style={{fontSize:11,textAlign:"center",marginTop:18}}>访问令牌有效期 15 分钟，刷新凭证保存在 HttpOnly Cookie 中。</p>
    </div>
  </main>;
}
