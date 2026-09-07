"use client";
import { AppImage } from "../components/AppImage";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "../components/AppShell";
import { apiRequest, fetchWardrobe, WardrobeItem, wardrobeImage } from "../lib/wardrobeApi";
import { DEFAULT_WEATHER_CITY, readWeatherCity, saveWeatherCity } from "../lib/weatherCity";

type Day={date:string;occasion:string;item_ids:string[];reason:string;warnings?:string[]};
type Week={plan_id:string;days:Day[];laundry_windows:string[]};
type Travel={destination:string;packing_item_ids:string[];daily_outfits:Day[];emergency_plan:string[];missing_items:string[]};
type Integration={provider:string;status:string};
type History={id:number;worn_at:string;occasion:string|null;item_ids:string[]};
type OutlookEvent={subject:string;start:{dateTime:string};end:{dateTime:string};location?:{displayName?:string};isAllDay:boolean};
const iso=(date:Date)=>date.toISOString().slice(0,10);

export default function Plan(){
  const [items,setItems]=useState<WardrobeItem[]>([]),[integrations,setIntegrations]=useState<Integration[]>([]),[history,setHistory]=useState<History[]>([]),[outlookEvents,setOutlookEvents]=useState<OutlookEvent[]>([]),[request,setRequest]=useState(""),[week,setWeek]=useState<Week|null>(null),[travel,setTravel]=useState<Travel|null>(null),[notice,setNotice]=useState(""),[busy,setBusy]=useState(false),[advanced,setAdvanced]=useState(false);
  const [startDate,setStartDate]=useState(iso(new Date())),[city,setCity]=useState(DEFAULT_WEATHER_CITY),[temperature,setTemperature]=useState(24),[rain,setRain]=useState(20);
  useEffect(()=>{const savedCity=readWeatherCity();Promise.all([fetchWardrobe(),apiRequest<Integration[]>("/api/v1/integrations"),apiRequest<History[]>("/api/v1/calendar")]).then(([wardrobe,connections,records])=>{setCity(savedCity);setItems(wardrobe);setIntegrations(connections);setHistory(records)}).catch(error=>setNotice(error.message))},[]);
  useEffect(()=>{if(integrations.some(item=>item.provider==="outlook"&&item.status==="connected"))apiRequest<OutlookEvent[]>("/api/v1/integrations/outlook/events?days=14").then(setOutlookEvents).catch(error=>setNotice(error.message))},[integrations]);
  const byId=useMemo(()=>new Map(items.map(item=>[item.id,item])),[items]);
  const weather={city,temperature_c:temperature,feels_like_c:temperature,rain_probability:rain/100,wind_level:2,condition:rain>=50?"有雨":"多云"};
  const destination=()=>request.match(/(?:去|到)([\u4e00-\u9fa5A-Za-z]{2,12})(?:出差|旅行|旅游|玩)/)?.[1]||city;
  const dayCount=()=>Number(request.match(/(\d+)天/)?.[1]||3);

  async function run(){
    if(!request.trim()){setNotice("先告诉我接下来有什么安排");return} setBusy(true);setNotice("");setWeek(null);setTravel(null);
    try{
      saveWeatherCity(city);const activeWeather=advanced?weather:await apiRequest<typeof weather>(`/api/v1/weather/current?city=${encodeURIComponent(city)}`);
      if(/旅行|旅游|出差|行李|收拾/.test(request)){
        const count=Math.min(14,Math.max(2,dayCount())),start=new Date(`${startDate}T12:00:00`),place=destination();
        const days=Array.from({length:count},(_,index)=>{const date=new Date(start);date.setDate(date.getDate()+index);return{date:iso(date),occasion:/出差/.test(request)?"出差":"旅行",formality_level:/会议|客户/.test(request)?3:2,weather:{...activeWeather,city:place},notes:[request]}});
        setTravel(await apiRequest("/api/v1/travel-plans",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({destination:place,start_date:startDate,end_date:days.at(-1)?.date||startDate,days,laundry_available:true,luggage_size:"登机箱",max_items:12})}));
        setNotice("旅行清单和每天的穿搭已经整理好");
      }else if(/提醒|面试|会议|日程/.test(request)){
        const connected=integrations.some(item=>item.provider==="outlook"&&item.status==="connected");
        if(!connected){setNotice("要创建日程提醒，请先在“我的”中连接日历只读权限");return}
        const when=new Date(Date.now()+86400000); await apiRequest("/api/v1/proactive/events",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({event_type:"calendar_event",scheduled_for:when.toISOString(),importance:.8,payload:{title:request,weather:activeWeather},source_scope:"outlook:Calendars.Read"})}); setNotice("已经记录这个重要安排，会在合适的时间提醒你准备穿搭");
      }else{
        const start=new Date(`${startDate}T12:00:00`),days=Array.from({length:7},(_,index)=>{const date=new Date(start);date.setDate(date.getDate()+index);const dateKey=iso(date),event=outlookEvents.find(value=>value.start.dateTime.slice(0,10)===dateKey),weekend=[0,6].includes(date.getDay());return{date:dateKey,occasion:event?.subject||(weekend?"周末休闲":"日常通勤"),formality_level:event&&/会议|面试|客户|商务/.test(event.subject)?4:weekend?2:3,weather:activeWeather,notes:[request,event?.location?.displayName||""]}});
        setWeek(await apiRequest("/api/v1/weekly-plans",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({start_date:startDate,days,reuse_target:2,avoid_consecutive_repeat:true})})); setNotice("未来 7 天已经安排好");
      }
    }catch(error){setNotice(error instanceof Error?error.message:"规划失败")}finally{setBusy(false)}
  }
  const images=(ids:string[])=><div className="toolbar">{ids.map(id=>{const item=byId.get(id);return item&&wardrobeImage(item)?<AppImage key={id} src={wardrobeImage(item)} alt={item.subcategory} title={item.subcategory} style={{width:58,height:64,objectFit:"contain",borderRadius:10,background:"#fff"}}/>:null})}</div>;
  return <AppShell title="计划"><h1 className="title">接下来穿什么</h1><p className="subtle">一周安排、旅行打包和重要日程，都可以直接告诉我。</p>
    <div className="agent-box" style={{marginTop:20}}><input value={request} onChange={event=>setRequest(event.target.value)} onKeyDown={event=>event.key==="Enter"&&run()} placeholder="例如：周五去杭州出差三天，帮我收拾衣服"/><button className="button button-primary" onClick={run} disabled={busy}>{busy?"正在安排…":"开始安排"}</button><div className="quick-prompts">{["安排下周上班穿搭","周五出差三天，帮我收拾衣服","明天面试，提前提醒我"].map(value=><button key={value} onClick={()=>setRequest(value)}>{value}</button>)}<button onClick={()=>setAdvanced(value=>!value)}>调整天气</button></div></div>
    {advanced&&<div className="card form-grid plan-details"><div className="field"><label>开始日期</label><input className="input" type="date" value={startDate} onChange={event=>setStartDate(event.target.value)}/></div><div className="field"><label>城市</label><input className="input" value={city} onChange={event=>setCity(event.target.value)}/></div><div className="field"><label>气温</label><input className="input" type="number" value={temperature} onChange={event=>setTemperature(Number(event.target.value))}/></div><div className="field"><label>降雨概率</label><input className="input" type="number" value={rain} onChange={event=>setRain(Number(event.target.value))}/></div></div>}
    {notice&&<div className="try-on-message">{notice}</div>}
    {week&&<div className="week-strip" style={{marginTop:20}}>{week.days.map(day=><article className="week-day" key={day.date}><b>{day.date.slice(5)} · {day.occasion}</b>{images(day.item_ids)}<p className="subtle">{day.reason}</p></article>)}</div>}
    {travel&&<><section className="card" style={{marginTop:20}}><h2>{travel.destination} · 带这 {travel.packing_item_ids.length} 件</h2>{images(travel.packing_item_ids)}</section><div className="grid grid-2" style={{marginTop:16}}>{travel.daily_outfits.map(day=><article className="card" key={day.date}><b>{day.date} · {day.occasion}</b>{images(day.item_ids)}<p className="subtle">{day.reason}</p></article>)}</div>{travel.missing_items.length>0&&<div className="card"><h3>可能缺少</h3>{travel.missing_items.map(value=><p key={value}>{value}</p>)}</div>}</>}
    {outlookEvents.length>0&&<details className="card plan-details"><summary>Outlook 近期日程（只读）</summary>{outlookEvents.slice(0,8).map((event,index)=><p className="subtle" key={`${event.start.dateTime}-${index}`}>{new Date(event.start.dateTime).toLocaleString()} · {event.subject}{event.location?.displayName?` · ${event.location.displayName}`:""}</p>)}</details>}
    <details className="card plan-details"><summary>最近穿搭记录</summary>{history.slice(0,6).map(row=><div className="item-row" key={row.id}><div><b>{new Date(row.worn_at).toLocaleDateString()} · {row.occasion||"日常"}</b>{images(row.item_ids)}</div></div>)}{!history.length&&<p className="subtle">还没有穿搭记录。</p>}</details>
  </AppShell>
}
