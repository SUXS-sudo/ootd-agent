"use client";
import { AppImage } from "../components/AppImage";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "../components/AppShell";
import { DEFAULT_FEMALE_MODEL } from "../components/FemaleModelPicker";
import { API_URL, apiRequest, fetchWardrobe, WardrobeItem, wardrobeImage } from "../lib/wardrobeApi";
import { buildOutfitTryOnPrompt } from "../lib/tryonPrompt";
import { DEFAULT_WEATHER_LOCATION, readWeatherLocation, saveWeatherLocation, WEATHER_LOCATIONS, WeatherLocation } from "../lib/weatherCity";

type Outfit = {
  outfit_id?: string; title: string; kind: string; item_ids: string[]; reason: string;
  wearing_tips?: string[]; warnings?: string[]; scores?: Record<string, number>;
};
type AgentMode = "auto" | "fast";
type CalendarEntry = { outfit_id: string; worn_at: string };
type Weather = { date?:string; city:string; district?:string; temperature_c:number; feels_like_c:number; temperature_max_c?:number;temperature_min_c?:number;rain_probability:number; wind_level:number; condition:string };
type OutlookEvent={id?:string;subject:string;start:{dateTime:string};end:{dateTime:string};location?:{displayName?:string};isAllDay:boolean};
const EDITABLE_CALENDAR_KEY="ootd.editable-calendar";
const localDate=(date:Date)=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
const weatherPath=(value:WeatherLocation,date:string)=>`/api/v1/weather/current?city=${encodeURIComponent(value.city)}&district=${encodeURIComponent(value.district)}&latitude=${value.latitude}&longitude=${value.longitude}&date=${date}`;
const readEditableEvents=()=>{try{const saved=localStorage.getItem(EDITABLE_CALENDAR_KEY);return saved?JSON.parse(saved) as OutlookEvent[]:[]}catch{return[]}};
const modeOptions: { value: AgentMode; label: string; hint: string }[] = [
  { value: "auto", label: "自动", hint: "普通需求智能精选，复杂描述自动深度理解" },
  { value: "fast", label: "优先速度", hint: "只使用本地规则，响应最快" },
];

async function makeOutfitReference(itemIds: string[], wardrobe: WardrobeItem[]) {
  const selected = itemIds.map(id => wardrobe.find(item => item.id === id)).filter(Boolean) as WardrobeItem[];
  const canvas = document.createElement("canvas"); canvas.width = 1200; canvas.height = Math.max(900, Math.ceil(selected.length / 4) * 430);
  const ctx = canvas.getContext("2d"); if (!ctx) throw new Error("无法创建搭配参考图");
  ctx.fillStyle = "#f5f1e8"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  const images = await Promise.all(selected.map(async item => { const image = new Image(); image.crossOrigin = "use-credentials"; image.src = wardrobeImage(item); await new Promise<void>((resolve, reject) => { image.onload = () => resolve(); image.onerror = () => reject(new Error(`衣物图片加载失败：${item.subcategory}`)); }); return image; }));
  const width = 1200 / Math.min(4, images.length);
  images.forEach((image, index) => { const x = index % 4 * width, y = Math.floor(index / 4) * 430, scale = Math.min((width - 36) / image.width, 350 / image.height); ctx.drawImage(image, x + (width - image.width * scale) / 2, y + 42 + (350 - image.height * scale) / 2, image.width * scale, image.height * scale); });
  const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error("无法导出搭配参考图")), "image/png"));
  return new File([blob], "outfit.png", { type: "image/png" });
}

export default function Today() {
  const [wardrobe, setWardrobe] = useState<WardrobeItem[]>([]);
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [active, setActive] = useState(0);
  const [request, setRequest] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [adopted, setAdopted] = useState("");
  const [tryon, setTryon] = useState("");
  const [selectedItem, setSelectedItem] = useState<WardrobeItem | null>(null);
  const [replacementItem, setReplacementItem] = useState<WardrobeItem | null>(null);
  const [mode, setMode] = useState<AgentMode>("auto");
  const [location, setLocation] = useState<WeatherLocation>(DEFAULT_WEATHER_LOCATION);
  const [weather, setWeather] = useState<Weather>({city:DEFAULT_WEATHER_LOCATION.city,district:DEFAULT_WEATHER_LOCATION.district,temperature_c:22,feels_like_c:22,rain_probability:.2,wind_level:2,condition:"天气读取中"});
  const [selectedDate,setSelectedDate]=useState(localDate(new Date()));
  const [outlookEvents,setOutlookEvents]=useState<OutlookEvent[]>([]);
  const [usingDemoCalendar,setUsingDemoCalendar]=useState(false);
  const [calendarEnabled,setCalendarEnabled]=useState(true);
  const [editingCalendar,setEditingCalendar]=useState(false);
  const [editingEventId,setEditingEventId]=useState<string|null>(null);
  const [eventDraft,setEventDraft]=useState({subject:"",date:localDate(new Date()),start:"09:00",end:"10:00",location:""});
  const viewingToday=selectedDate===localDate(new Date());
  const temperatureRange=weather.temperature_min_c!==undefined
    ? `${Math.round(weather.temperature_min_c)}–${Math.round(weather.temperature_max_c??weather.temperature_c)}℃`
    : null;
  const temperatureSummary=temperatureRange
    ? viewingToday
      ? `${temperatureRange} · 当前 ${Math.round(weather.temperature_c)}℃ · 体感 ${Math.round(weather.feels_like_c)}℃`
      : `${temperatureRange} · 预报均温 ${Math.round(weather.temperature_c)}℃ · 预报体感约 ${Math.round(weather.feels_like_c)}℃`
    : `${viewingToday?"当前":"预报均温"} ${Math.round(weather.temperature_c)}℃ · ${viewingToday?"体感":"预报体感约"} ${Math.round(weather.feels_like_c)}℃`;

  useEffect(() => { const savedLocation=readWeatherLocation(),today=localDate(new Date());Promise.all([fetchWardrobe(),apiRequest<Weather>(weatherPath(savedLocation,today)),apiRequest<{provider:string;status:string}[]>("/api/v1/integrations")]).then(async([items,currentWeather,integrations])=>{setLocation(savedLocation);setWardrobe(items);setWeather(currentWeather);const connected=integrations.some(value=>value.provider==="outlook"&&value.status==="connected"),outlook=connected?await apiRequest<OutlookEvent[]>("/api/v1/integrations/outlook/events?days=7"):[],events=connected?outlook:readEditableEvents(),todayEvents=events.filter(value=>value.start.dateTime.slice(0,10)===today),eventText=todayEvents.map(value=>`${value.start.dateTime.slice(11,16)} ${value.subject}`).join("；"),formality=todayEvents.some(value=>/客户|面试|正式|汇报|婚礼/.test(value.subject))?4:3,walking=todayEvents.some(value=>/步行|园区|逛街|徒步/.test(value.subject))?60:30;setOutlookEvents(events);setUsingDemoCalendar(!connected);const generated=await apiRequest<{outfits:Outfit[]}>("/api/v1/outfits/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({occasion:eventText?`当天日程：${eventText}`:"日常",formality_level:formality,walking_minutes:walking,indoor_ratio:.8,mode:"balanced",temporary_requirements:eventText?[`当天日程：${eventText}`]:[],weather:currentWeather})});setOutfits(generated.outfits);setMessage(eventText?"已根据今天的天气和日程生成推荐":"已根据今天的天气生成推荐；你也可以添加日程让结果更贴合")}).catch(error=>setMessage(error.message)); }, []);
  const outfit = outfits[active];
  const items = outfit ? outfit.item_ids.map(id => wardrobe.find(value => value.id === id)).filter(Boolean) as WardrobeItem[] : [];
  const replacementCandidates = selectedItem ? wardrobe.filter(item => item.id !== selectedItem.id && !outfit?.item_ids.includes(item.id) && item.category === selectedItem.category && item.clean_status === "可穿" && item.image_url && (!(["上装", "外套"].includes(selectedItem.category)) || item.wearing_layer === selectedItem.wearing_layer)) : [];

  async function changeWeatherLocation(value:WeatherLocation) {
    setLocation(value);saveWeatherLocation(value);
    try{setMessage("正在更新天气并重新搭配…");const nextWeather=await apiRequest<Weather>(weatherPath(value,selectedDate));setWeather(nextWeather);setOutfits([]);await generate(request,[],nextWeather,dateEvents,calendarEnabled)}catch(error){setMessage(error instanceof Error?error.message:"天气读取失败")}
  }
  async function changeDate(value:string){setSelectedDate(value);try{setMessage("正在读取当天条件并重新搭配…");const nextWeather=await apiRequest<Weather>(weatherPath(location,value)),nextEvents=outlookEvents.filter(event=>event.start.dateTime.slice(0,10)===value);setWeather(nextWeather);setOutfits([]);await generate(request,[],nextWeather,nextEvents,calendarEnabled)}catch(error){setMessage(error instanceof Error?error.message:"天气读取失败")}}
  const province=WEATHER_LOCATIONS.find(value=>value.name===location.province)||WEATHER_LOCATIONS[0];
  const locationCity=province.cities.find(value=>value.name===location.city)||province.cities[0];
  const dateEvents=outlookEvents.filter(value=>value.start.dateTime.slice(0,10)===selectedDate);
  const dateOptions=Array.from({length:7},(_,index)=>{const date=new Date();date.setDate(date.getDate()+index);return{value:localDate(date),label:index===0?"今天":index===1?"明天":`${date.getMonth()+1}/${date.getDate()}`}});

  async function generate(instruction = request, locked: string[] = [],contextWeather=weather,contextEvents=dateEvents,useCalendar=calendarEnabled) {
    setLoading(true); setMessage("正在查看天气和衣橱…"); setAdopted(""); setTryon("");
    try {
      const eventContext=useCalendar&&contextEvents.length?contextEvents.map(value=>`${value.start.dateTime.slice(11,16)} ${value.subject}${value.location?.displayName?`（${value.location.displayName}）`:""}`).join("；"):"";
      const combined=[instruction,eventContext&&`当天日程：${eventContext}`].filter(Boolean).join("；");
      const formality=contextEvents.some(value=>/客户|面试|正式|汇报|婚礼/.test(value.subject))?4:contextEvents.some(value=>/上班|通勤|会议/.test(value.subject))?3:2,walking=contextEvents.some(value=>/步行|园区|逛街|徒步/.test(`${value.subject} ${value.location?.displayName||""}`))?60:30;
      const effectiveMode=mode==="fast"?"fast":combined.length>=24?"deep":"balanced";
      const data = await apiRequest<{ outfits: Outfit[] }>("/api/v1/outfits/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ occasion: combined || "日常",formality_level:useCalendar?formality:3,walking_minutes:useCalendar?walking:30,indoor_ratio:contextEvents.some(value=>/户外|园区/.test(value.location?.displayName||""))?.45:.8, mode:effectiveMode, locked_item_ids: locked, temporary_requirements: combined ? [combined] : [], weather:contextWeather }) });
      setOutfits(data.outfits); setActive(0); setMessage("已经从你的衣橱中选好一套");
    } catch (error) { setMessage(error instanceof Error ? error.message : "推荐失败"); }
    finally { setLoading(false); }
  }

  function beginNewEvent(){setEditingEventId(null);setEventDraft({subject:"",date:selectedDate,start:"09:00",end:"10:00",location:""});setEditingCalendar(true)}
  function beginEditEvent(event:OutlookEvent){setEditingEventId(event.id||null);setEventDraft({subject:event.subject,date:event.start.dateTime.slice(0,10),start:event.start.dateTime.slice(11,16),end:event.end.dateTime.slice(11,16),location:event.location?.displayName||""});setEditingCalendar(true)}
  async function persistEditableEvents(next:OutlookEvent[],notice:string){localStorage.setItem(EDITABLE_CALENDAR_KEY,JSON.stringify(next));setOutlookEvents(next);setMessage(notice);const selected=next.filter(event=>event.start.dateTime.slice(0,10)===selectedDate);setOutfits([]);await generate(request,[],weather,selected,calendarEnabled)}
  async function saveEvent(){if(!eventDraft.subject.trim()){setMessage("请填写日程名称");return}if(eventDraft.end<=eventDraft.start){setMessage("结束时间需要晚于开始时间");return}const event:OutlookEvent={id:editingEventId||crypto.randomUUID(),subject:eventDraft.subject.trim(),start:{dateTime:`${eventDraft.date}T${eventDraft.start}:00`},end:{dateTime:`${eventDraft.date}T${eventDraft.end}:00`},location:{displayName:eventDraft.location.trim()},isAllDay:false};const next=editingEventId?outlookEvents.map(value=>value.id===editingEventId?event:value):[...outlookEvents,event];setEditingEventId(null);setEventDraft({subject:"",date:selectedDate,start:"09:00",end:"10:00",location:""});await persistEditableEvents(next.sort((a,b)=>a.start.dateTime.localeCompare(b.start.dateTime)),"日程已保存，正在按新日程重新搭配")}
  async function deleteEvent(event:OutlookEvent){if(!window.confirm(`删除日程“${event.subject}”吗？`))return;await persistEditableEvents(outlookEvents.filter(value=>value.id!==event.id),"日程已删除，正在重新搭配")}

  async function replaceSelected() {
    if (!outfit?.outfit_id || !selectedItem || !replacementItem) return;
    setLoading(true); setMessage("只调整这件衣服，其他衣物保持不变…");
    try {
      const updated = await apiRequest<Outfit>("/api/v1/outfits/replace-item", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ outfit_id: outfit.outfit_id, item_id: selectedItem.id, mode: "custom", replacement_item_id: replacementItem.id }) });
      setOutfits(values => values.map((value, index) => index === active ? updated : value)); setSelectedItem(null); setReplacementItem(null); setMessage(`已换成「${replacementItem.subcategory}」，其他衣物没有改变`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "替换失败"); }
    finally { setLoading(false); }
  }

  async function record(adopt: boolean) {
    if (!outfit?.outfit_id) return;
    setLoading(true);
    try {
      let replaceToday = false;
      if (adopt) {
        const calendar = await apiRequest<CalendarEntry[]>("/api/v1/calendar");
        const today = new Date().toDateString();
        const existing = calendar.find(entry => new Date(entry.worn_at).toDateString() === today && entry.outfit_id !== outfit.outfit_id);
        if (existing && !window.confirm("今天已经记录了一套穿搭，是否替换为当前这套？")) { setMessage("已保留今天原来的穿搭"); return; }
        replaceToday = Boolean(existing);
      }
      const result = await apiRequest<{ replaced_today?: boolean }>("/api/v1/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ outfit_id: outfit.outfit_id, adopted: adopt, replace_today: replaceToday, feedback_tags: [adopt ? "喜欢整体搭配" : "不符合今天需求"], replaced_item_ids: [] }) });
      if (adopt) { setAdopted(outfit.outfit_id); setMessage(result.replaced_today ? "已替换今天的穿搭，穿着次数已同步更新" : "已记入今天的穿搭，衣物次数和偏好也已更新"); }
      else { setMessage("已记录不喜欢，正在换一套"); await generate(request); }
    } catch (error) { setMessage(error instanceof Error ? error.message : "记录失败"); }
    finally { setLoading(false); }
  }

  async function previewTryon() {
    if (!outfit) return;
    setLoading(true); setMessage("正在生成试穿效果…");
    try {
      const person = await (await fetch(DEFAULT_FEMALE_MODEL)).blob(); const garment = await makeOutfitReference(outfit.item_ids, wardrobe); const form = new FormData();
      form.append("person", new File([person], "model.jpg", { type: person.type || "image/jpeg" })); form.append("garment", garment); form.append("prompt", buildOutfitTryOnPrompt(outfit.item_ids, wardrobe));
      const data = await apiRequest<{ result_url: string }>("/api/v1/try-on/generate", { method: "POST", body: form }); setTryon(data.result_url.startsWith("http") ? data.result_url : `${API_URL}${data.result_url}`); setMessage("试穿效果已生成");
    } catch (error) { setMessage(error instanceof Error ? error.message : "试穿失败"); }
    finally { setLoading(false); }
  }

  return <AppShell title="今天">
    <section className="today-hero">
      <div><p className="today-date">{dateOptions.find(value=>value.value===selectedDate)?.label} · {weather.city}{weather.district?` ${weather.district}`:""} · {Math.round(weather.temperature_c)}℃ · {weather.condition}</p><div className="weather-city-picker"><select className="filter" aria-label="省份或直辖市" value={location.province} onChange={event=>{const nextProvince=WEATHER_LOCATIONS.find(value=>value.name===event.target.value)||WEATHER_LOCATIONS[0],nextCity=nextProvince.cities[0],district=nextCity.districts[0];void changeWeatherLocation({province:nextProvince.name,city:nextCity.name,...district,district:district.name})}}>{WEATHER_LOCATIONS.map(value=><option key={value.name}>{value.name}</option>)}</select>{(province.cities.length>1||province.cities[0].name!==province.name)&&<select className="filter" aria-label="城市" value={location.city} onChange={event=>{const nextCity=province.cities.find(value=>value.name===event.target.value)||province.cities[0],district=nextCity.districts[0];void changeWeatherLocation({province:province.name,city:nextCity.name,...district,district:district.name})}}>{province.cities.map(value=><option key={value.name}>{value.name}</option>)}</select>}<select className="filter" aria-label="区县" value={location.district} onChange={event=>{const district=locationCity.districts.find(value=>value.name===event.target.value)||locationCity.districts[0];void changeWeatherLocation({...location,...district,district:district.name})}}>{locationCity.districts.map(value=><option key={value.name}>{value.name}</option>)}</select></div><h1>今天想怎么穿？</h1><p className="subtle">说场合、颜色或舒适度要求，我只会使用你衣橱里的衣服。</p></div>
    </section>

    <section className="daily-context card-flat">
      <div className="date-switch">{dateOptions.map(value=><button key={value.value} className={selectedDate===value.value?"active":""} onClick={()=>changeDate(value.value)}>{value.label}</button>)}</div>
      <div className="context-grid"><div><span className="eyebrow">天气 · Open-Meteo</span><b>{temperatureSummary} · {weather.condition}</b><p className="subtle">降雨概率 {Math.round(weather.rain_probability*100)}% · 风速 {Math.round(weather.wind_level)} km/h</p></div><div><div className="context-title"><span className="eyebrow">日程 · {usingDemoCalendar?"手工填写":"Outlook"}</span><label><input type="checkbox" checked={calendarEnabled} onChange={event=>{const enabled=event.target.checked;setCalendarEnabled(enabled);setOutfits([]);void generate(request,[],weather,dateEvents,enabled)}}/> 参考日程</label></div>{usingDemoCalendar&&!dateEvents.length&&<p className="pill orange">尚未连接或填写日程；当前推荐只参考天气和你的输入</p>}{calendarEnabled&&dateEvents.length?dateEvents.map((value,index)=><p key={`${value.start.dateTime}-${index}`}><b>{value.start.dateTime.slice(11,16)}</b> · {value.subject}{value.location?.displayName?` · ${value.location.displayName}`:""}</p>):<p className="subtle">当天没有日程</p>}</div></div>
    </section>

    {usingDemoCalendar&&<section className="editable-calendar card"><div className="section-head"><div><span className="eyebrow">日程 · 我的数据</span><h2>编辑日程</h2><p className="subtle">这些安排只保存在当前浏览器，会用于判断正式度、步行量和场景。</p></div><button className="button button-ghost" onClick={()=>editingCalendar?setEditingCalendar(false):beginNewEvent()}>{editingCalendar?"收起":"＋ 添加日程"}</button></div>{editingCalendar&&<div className="calendar-editor"><div className="form-grid"><div className="field"><label>日程名称</label><input className="input" value={eventDraft.subject} onChange={event=>setEventDraft({...eventDraft,subject:event.target.value})} placeholder="例如：客户会议"/></div><div className="field"><label>地点</label><input className="input" value={eventDraft.location} onChange={event=>setEventDraft({...eventDraft,location:event.target.value})} placeholder="例如：办公室"/></div><div className="field"><label>日期</label><input className="input" type="date" value={eventDraft.date} onChange={event=>setEventDraft({...eventDraft,date:event.target.value})}/></div><div className="field"><label>时间</label><div className="calendar-time-row"><input className="input" type="time" value={eventDraft.start} onChange={event=>setEventDraft({...eventDraft,start:event.target.value})}/><span>至</span><input className="input" type="time" value={eventDraft.end} onChange={event=>setEventDraft({...eventDraft,end:event.target.value})}/></div></div></div><div className="toolbar"><button className="button button-primary" disabled={loading} onClick={()=>void saveEvent()}>{editingEventId?"保存修改":"添加日程"}</button>{editingEventId&&<button className="button button-ghost" onClick={beginNewEvent}>取消编辑</button>}</div></div>}<div className="editable-calendar-list">{outlookEvents.map(event=><div className="item-row" key={event.id||event.start.dateTime}><div><b>{new Date(event.start.dateTime).toLocaleString([], {month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})} · {event.subject}</b><p>{event.location?.displayName||"未填写地点"}</p></div><span className="spacer"/><button className="text-action" onClick={()=>beginEditEvent(event)}>编辑</button><button className="text-action danger" onClick={()=>void deleteEvent(event)}>删除</button></div>)}{!outlookEvents.length&&<p className="subtle">还没有日程，添加后系统会按安排重新推荐穿搭。</p>}</div></section>}

    <section className="agent-box">
      <input value={request} onChange={event => setRequest(event.target.value)} onKeyDown={event => event.key === "Enter" && generate()} placeholder="例如：今天上班，晚上约会，不想穿高跟鞋" />
      <button className="button button-primary" disabled={loading || !wardrobe.length} onClick={() => generate()}>{loading ? "正在搭配…" : "帮我搭配"}</button>
      <div className="mode-switch" aria-label="推荐模式">{modeOptions.map(option => <button type="button" key={option.value} className={mode === option.value ? "active" : ""} onClick={() => setMode(option.value)} title={option.hint}>{option.label}</button>)}<span>{modeOptions.find(option => option.value === mode)?.hint}</span></div>
      <div className="quick-prompts">{["上班", "约会", "休闲"].map(value => <button key={value} onClick={() => { setRequest(value); generate(value); }}>{value}</button>)}<Link href="/outfit-check">拍照检查</Link></div>
    </section>

    {!wardrobe.length && !message && <section className="card empty-state"><h2>先添加几件衣服</h2><p className="subtle">有了真实衣橱，我才能给你可直接穿出门的建议。</p><Link href="/wardrobe/upload" className="button button-primary">添加衣服</Link></section>}

    {outfit && <section className="main-recommendation">
      <div className="recommendation-head"><div><span className="pill green">{outfit.kind||"主推荐"}</span><h2>{outfit.title}</h2><p className="subtle">{outfit.reason}</p></div></div>
      <div className="main-outfit-items">{items.map(item => <button key={item.id} title={`调整${item.subcategory}`} className={selectedItem?.id===item.id?"selected-item":""} onClick={() => {setSelectedItem(item);setReplacementItem(null)}}><AppImage src={wardrobeImage(item)} alt={item.subcategory} /><b>{item.subcategory}</b><span>{item.category} · 点按更换</span></button>)}</div>
      {selectedItem&&<div className="replacement-panel card-flat"><div className="replacement-picker-head"><div><b>替换「{selectedItem.subcategory}」</b><p className="subtle">从衣橱中自己选择一件，其他衣物保持不变。</p></div><button className="text-action" onClick={()=>{setSelectedItem(null);setReplacementItem(null)}}>取消</button></div>{replacementCandidates.length?<div className="replacement-candidates">{replacementCandidates.map(item=><button type="button" key={item.id} className={`replacement-candidate ${replacementItem?.id===item.id?"selected":""}`} onClick={()=>setReplacementItem(item)}><AppImage src={wardrobeImage(item)} alt={item.subcategory}/><b>{item.subcategory}</b><span>{item.colors.join("/")||item.category}</span></button>)}</div>:<p className="replacement-drawer-empty">衣橱里暂时没有其他可替换的{selectedItem.category}</p>}<div className="replacement-picker-foot"><span className="subtle">{replacementItem?`已选择：${replacementItem.subcategory}`:"请先选择一件衣服"}</span><button className="button button-primary" disabled={!replacementItem||loading} onClick={replaceSelected}>{loading?"替换中…":"确认替换"}</button></div></div>}
      {outfits.length>1&&<div className="alternative-drawer"><h3>另外两套方案</h3>{outfits.map((value,index)=>index===active?null:<button key={value.outfit_id||index} onClick={()=>{setActive(index);setSelectedItem(null)}}><span className="alternative-images">{value.item_ids.map(id=>{const item=wardrobe.find(candidate=>candidate.id===id);return item?<AppImage key={id} src={wardrobeImage(item)} alt={item.subcategory} title={item.subcategory}/>:null})}</span><span className="alternative-copy"><b><span className="pill green">{value.kind}</span>{value.title}</b><span>{value.reason}</span><small>点击查看整套并进行替换或试穿</small></span></button>)}</div>}
      {!!outfit.wearing_tips?.length && <p className="wearing-tip">{outfit.wearing_tips.join(" · ")}</p>}
      <div className="primary-actions"><button className="button button-ghost" disabled={loading} onClick={previewTryon}>试穿看看</button><button className="button button-primary" disabled={loading || adopted === outfit.outfit_id} onClick={() => record(true)}>{adopted === outfit.outfit_id ? "✓ 已记入今天" : "今天穿这套"}</button><button className="text-action" disabled={loading} onClick={() => record(false)}>不喜欢</button></div>
    </section>}

    {tryon && <section className="tryon-simple"><div><h2>试穿效果</h2><p className="subtle">试穿只是预览，不会自动记录为今天穿着。</p></div><AppImage src={tryon} alt="虚拟试穿效果" /></section>}
    {message && <div className="try-on-message">{message}</div>}
    <div className="today-history-link"><Link href="/week-plan">查看计划和穿搭记录 →</Link></div>
  </AppShell>;
}
