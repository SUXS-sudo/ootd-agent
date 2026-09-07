"use client";
import { AppImage } from "../components/AppImage";
import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import { API_URL, apiRequest } from "../lib/wardrobeApi";

export default function TryOn() {
  const [person, setPerson] = useState<File | null>(null);
  const [garment, setGarment] = useState<File | null>(null);
  const [personPreview, setPersonPreview] = useState("/people/my-photo.jpg");
  const [garmentPreview, setGarmentPreview] = useState("");
  const [result, setResult] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => () => {
    if (personPreview.startsWith("blob:")) URL.revokeObjectURL(personPreview);
    if (garmentPreview.startsWith("blob:")) URL.revokeObjectURL(garmentPreview);
  }, [personPreview, garmentPreview]);

  const choosePerson = (file?: File) => {
    if (!file) return;
    setPerson(file); setPersonPreview(URL.createObjectURL(file)); setResult("");
  };
  const chooseGarment = (file?: File) => {
    if (!file) return;
    setGarment(file); setGarmentPreview(URL.createObjectURL(file)); setResult("");
  };
  const generate = async () => {
    if (!person || !garment) { setStatus("error"); setMessage("请先选择人物全身照和衣服参考图"); return; }
    setStatus("loading"); setMessage("正在生成真人换装照片，通常需要几十秒…");
    const form = new FormData(); form.append("person", person); form.append("garment", garment);
    try {
      const data = await apiRequest<{result_url:string;model:string}>("/api/v1/try-on/generate", { method: "POST", body: form });
      setResult(data.result_url.startsWith("http") ? data.result_url : `${API_URL}${data.result_url}`);
      setStatus("done"); setMessage(`换装完成 · ${data.model}`);
    } catch (error) {
      setStatus("error"); setMessage(error instanceof Error ? error.message : "换装失败，请稍后重试");
    }
  };

  return <AppShell title="高质量数字试穿">
    <div className="eyebrow">AI VIRTUAL TRY-ON</div>
    <h1 className="title">上传你的照片，试穿真实衣服。</h1>
    <p className="subtle">人物照建议正面全身、无遮挡；衣服参考图建议主体清晰、背景简单。</p>
    <div className="grid grid-3 try-on-workspace" style={{ marginTop: 24 }}>
      <label className="card try-on-source"><div className="eyebrow">01 · 我的照片</div><div className="try-on-source-photo"><AppImage src={personPreview} alt="人物全身照" /></div><input hidden type="file" accept="image/*" onChange={e => choosePerson(e.target.files?.[0])}/><span className="button button-soft">{person ? "更换人物照片" : "选择人物照片"}</span></label>
      <label className="card try-on-source"><div className="eyebrow">02 · 衣服参考</div><div className="try-on-source-photo garment-reference">{garmentPreview ? <AppImage src={garmentPreview} alt="衣服参考图" /> : <div className="upload-hint"><b>＋ 添加衣服照片</b><span>支持单品图或穿搭参考图</span></div>}</div><input hidden type="file" accept="image/*" onChange={e => chooseGarment(e.target.files?.[0])}/><span className="button button-soft">{garment ? "更换衣服照片" : "选择衣服照片"}</span></label>
      <div className="card try-on-source"><div className="eyebrow">03 · 换装结果</div><div className={`try-on-source-photo try-on-generated ${status === "loading" ? "is-loading" : ""}`}>{result ? <AppImage src={result} alt="AI 真人换装结果" /> : <div className="upload-hint"><b>{status === "loading" ? "正在生成…" : "等待生成"}</b><span>保留人物身份、姿态和背景</span></div>}</div><button className="button button-primary" disabled={status === "loading"} onClick={generate}>{status === "loading" ? "生成中…" : result ? "重新生成" : "生成换装照片"}</button></div>
    </div>
    {message && <div className={`try-on-message ${status}`}>{message}</div>}
  </AppShell>;
}
