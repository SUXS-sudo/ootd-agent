export const API_URL=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
export type WardrobeStatus="可穿"|"待洗"|"清洗中"|"晾晒中"|"收纳中"|"季节性收纳"|"借出"|"已淘汰"|"需要修补"|"准备淘汰";
export type WardrobeItem={id:string;user_id:string;category:string;subcategory:string;colors:string[];material_guess:string[];material_confidence:number;pattern:string;fit:string;length:string;wearing_layer?:"内搭"|"主上装"|"外搭"|"不可叠穿";warmth_level:number;formality_level:number;styles:string[];seasons:string[];weather_constraints:string[];clean_status:WardrobeStatus;image_url:string|null;wear_count:number;last_worn_at:string|null};
const TOKEN_KEY="ootd.access_token";
const readToken=()=>typeof window!=="undefined"?sessionStorage.getItem(TOKEN_KEY):null;
const saveToken=(token:string)=>{if(typeof window!=="undefined")sessionStorage.setItem(TOKEN_KEY,token)};
async function refreshToken(){const response=await fetch(`${API_URL}/api/v1/auth/refresh`,{method:"POST",credentials:"include"});if(!response.ok)return null;const data=await response.json();saveToken(data.access_token);return data.access_token as string}
function apiErrorMessage(data:unknown,status:number){
  const fallback=`后端请求失败 (${status})`;
  if(!data||typeof data!=="object")return fallback;
  const detail=(data as {detail?:unknown}).detail;
  if(typeof detail==="string")return detail;
  if(Array.isArray(detail))return detail.map(value=>{
    if(!value||typeof value!=="object")return String(value);
    const error=value as {loc?:unknown[];msg?:string};
    const field=error.loc?.filter(part=>part!=="body").join(" → ");
    return `${field?`${field}：`:""}${error.msg||"参数不正确"}`;
  }).join("；")||fallback;
  if(detail&&typeof detail==="object"){
    const error=detail as {message?:unknown;code?:unknown};
    if(typeof error.message==="string")return error.message;
    if(typeof error.code==="string")return `${error.code}（请求未完成）`;
    try{return JSON.stringify(detail)}catch{return fallback}
  }
  return fallback;
}
export async function apiRequest<T>(path:string,init?:RequestInit,retry=true):Promise<T>{const headers=new Headers(init?.headers);const token=readToken();if(token)headers.set("Authorization",`Bearer ${token}`);const response=await fetch(`${API_URL}${path}`,{...init,headers,credentials:"include"});if(response.status===401&&retry&&!path.startsWith("/api/v1/auth/")){const renewed=await refreshToken();if(renewed)return apiRequest<T>(path,init,false)}const data=await response.json().catch(()=>({}));if(response.status===401&&typeof window!=="undefined"&&!path.startsWith("/api/v1/auth/"))window.location.href="/login";if(!response.ok)throw new Error(apiErrorMessage(data,response.status));return data;}
export type LocalAuthResult={access_token:string;expires_in:number;user:{user_id:string;email:string}};
export async function localAuth(mode:"login"|"register",email:string,password:string){const result=await apiRequest<LocalAuthResult>(`/api/v1/auth/${mode}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})},false);saveToken(result.access_token);return result}
export async function localLogout(){try{await fetch(`${API_URL}/api/v1/auth/logout`,{method:"POST",credentials:"include"})}finally{if(typeof window!=="undefined")sessionStorage.removeItem(TOKEN_KEY)}}
export const wardrobeFallback=(item:WardrobeItem)=>item.category==="包袋"?"/clothes/item_7070-caramel-bag.png":item.category==="鞋履"?(/米白平底鞋|芭蕾平底鞋/.test(item.subcategory)?"/clothes/item-test-ivory-ballet-flats.png":item.colors.some(x=>/米白|奶油|杏仁/.test(x))?"/clothes/item_7100-beige-slingback.png":"/clothes/item_4011-white-sneakers.png"):"";
export const wardrobeImage=(item:WardrobeItem)=>item.image_url?(item.image_url.startsWith("/api/")||item.image_url.startsWith("/generated/")?`${API_URL}${item.image_url}`:item.image_url):wardrobeFallback(item);
export const fetchWardrobe=()=>apiRequest<WardrobeItem[]>("/api/v1/wardrobe");
export const fetchWardrobeItem=(id:string)=>apiRequest<WardrobeItem>(`/api/v1/wardrobe/${id}`);
export const updateWardrobeItem=(id:string,item:WardrobeItem)=>apiRequest<WardrobeItem>(`/api/v1/wardrobe/${id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({category:item.category,subcategory:item.subcategory,colors:item.colors,material_guess:item.material_guess,material_confidence:item.material_confidence,pattern:item.pattern,fit:item.fit,length:item.length,wearing_layer:item.wearing_layer||"主上装",warmth_level:item.warmth_level,formality_level:item.formality_level,styles:item.styles,seasons:item.seasons,weather_constraints:item.weather_constraints,clean_status:item.clean_status,image_url:item.image_url})});
export const deleteWardrobeItem=(id:string)=>apiRequest<void>(`/api/v1/wardrobe/${id}`,{method:"DELETE"});
export const updateWardrobeStatus=(id:string,status:string)=>apiRequest<{item_id:string;status:string;equivalent_replanned_dates:string[]}>(`/api/v1/wardrobe/${id}/status?value=${encodeURIComponent(status)}`,{method:"PATCH"});
type SignedUpload={asset_id:string;object_key:string;upload_url:string;expires_in:number;headers:Record<string,string>};
const csv=(value:FormDataEntryValue|null)=>String(value||"").split(/[,，]/).map(x=>x.trim()).filter(Boolean);
export async function uploadWardrobeItem(form:FormData){
  const file=form.get("file");if(!(file instanceof File))throw new Error("请选择衣物图片");
  const signed=await apiRequest<SignedUpload>("/api/v1/uploads/sign",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename:file.name||"item.jpg",content_type:file.type||"image/jpeg",byte_size:file.size,kind:"wardrobe"})});
  if(signed.upload_url.startsWith("/"))await apiRequest<void>(signed.upload_url,{method:"PUT",headers:signed.headers,body:file});
  else{const uploaded=await fetch(signed.upload_url,{method:"PUT",headers:signed.headers,body:file});if(!uploaded.ok)throw new Error(`图片直传失败 (${uploaded.status})`)}
  return apiRequest<WardrobeItem>("/api/v1/wardrobe/from-upload",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset_id:signed.asset_id,category:String(form.get("category")||""),subcategory:String(form.get("subcategory")||""),color:String(form.get("color")||"未标注"),material_guess:csv(form.get("material_guess")),material_confidence:Number(form.get("material_confidence")||0),pattern:String(form.get("pattern")||"待确认"),fit:String(form.get("fit")||"常规"),length:String(form.get("length")||"待确认"),wearing_layer:String(form.get("wearing_layer")||"主上装"),warmth_level:Number(form.get("warmth_level")||2),formality_level:Number(form.get("formality_level")||3),styles:csv(form.get("styles")),seasons:csv(form.get("seasons")),weather_constraints:csv(form.get("weather_constraints")),clean_status:String(form.get("clean_status")||"可穿")})});
}
export type WardrobeSuggestion={category:string;subcategory:string;color:string;material_guess:string[];material_confidence:number;pattern:string;length:string;weather_constraints:string[];wearing_layer:string;fit:string;warmth_level:number;formality_level:number;seasons:string[];styles:string[];confidence:{category:number;color:number};generated_by:string;crop_image_data?:string;crop_mime_type?:string};
export const analyzeWardrobePhoto=(file:File)=>{const form=new FormData();form.set("file",file);return apiRequest<WardrobeSuggestion>("/api/v1/wardrobe/analyze",{method:"POST",body:form})};
export type OutfitWardrobeAnalysis={items:WardrobeSuggestion[];generated_by:string;notice:string};
export const analyzeOutfitForWardrobe=(file:File)=>{const form=new FormData();form.set("file",file);return apiRequest<OutfitWardrobeAnalysis>("/api/v1/wardrobe/analyze-outfit",{method:"POST",body:form})};
export type WardrobeLinkImport={filename:string;mime_type:string;image_data:string;suggestion:WardrobeSuggestion;source_url:string};
export const importWardrobeLink=(url:string)=>{const form=new FormData();form.set("url",url);return apiRequest<WardrobeLinkImport>("/api/v1/wardrobe/import-link",{method:"POST",body:form})};
export const renderCleanWardrobeImage=(file:File,item:{subcategory:string;category:string;color:string})=>{const form=new FormData();form.set("file",file);form.set("name",item.subcategory);form.set("category",item.category);form.set("color",item.color);return apiRequest<{status:string;model:string;result_url:string}>("/api/v1/wardrobe/render-clean",{method:"POST",body:form})};
