"use client";
import { AppImage } from "./AppImage";

import { ChangeEvent, useEffect, useState } from "react";

export const FEMALE_MODEL_STORAGE_KEY = "ootd-female-model";
export const DEFAULT_FEMALE_MODEL = "/people/models/woman-casual-01.png";

const presetModels = [
  { id: "woman-01", name: "女模特 A", src: "/people/models/woman-casual-01.png" },
  { id: "woman-02", name: "女模特 B", src: "/people/models/woman-casual-02.png" },
];

export type FemaleModelSelection = { id: string; name: string; src: string };

export function readFemaleModel(): FemaleModelSelection {
  if (typeof window === "undefined") return presetModels[0];
  try {
    const saved = JSON.parse(localStorage.getItem(FEMALE_MODEL_STORAGE_KEY) || "null");
    if (saved?.src) return saved;
  } catch { /* use the default model */ }
  return presetModels[0];
}

export function FemaleModelPicker({ onChange }: { onChange?: (model: FemaleModelSelection) => void }) {
  const [selected, setSelected] = useState<FemaleModelSelection>(presetModels[0]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const saved = readFemaleModel();
      setSelected(saved);
      onChange?.(saved);
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function select(model: FemaleModelSelection) {
    setSelected(model);
    try { localStorage.setItem(FEMALE_MODEL_STORAGE_KEY, JSON.stringify(model)); } catch { /* selection still works for this session */ }
    onChange?.(model);
  }

  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => select({ id: "custom-woman", name: "我的女模特", src: String(reader.result) });
    reader.readAsDataURL(file);
    event.target.value = "";
  }

  const options = selected.id === "custom-woman" ? [...presetModels, selected] : presetModels;
  return <section className="card model-picker">
    <div className="model-picker-heading">
      <div><div className="eyebrow">FEMALE MODEL</div><h2>选择模特图片</h2><p className="subtle">选定后，后续所有衣服都会沿用这位女模特。</p></div>
      <span className="pill green">仅女性</span>
    </div>
    <div className="model-picker-options">
      {options.map(model => <button type="button" key={model.id} className={`model-card ${selected.id === model.id ? "active" : ""}`} onClick={() => select(model)}>
        <AppImage src={model.src} alt={model.name} /><span>{model.name}</span>{selected.id === model.id && <b>✓</b>}
      </button>)}
      <label className="model-upload"><input hidden type="file" accept="image/*" onChange={upload}/><span>＋</span><strong>上传女模特</strong><small>建议正面全身照</small></label>
    </div>
  </section>;
}
