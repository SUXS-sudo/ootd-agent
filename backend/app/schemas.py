from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from .wardrobe_status import WardrobeStatus

class ProfileIn(BaseModel):
    height_cm:int|None=None; temperature_preference:str=""; preferred_styles:list[str]=[]; avoided_styles:list[str]=[]; preferred_item_terms:list[str]=[]; avoided_item_terms:list[str]=[]; preferred_colors:list[str]=[]; avoided_colors:list[str]=[]; restrictions:list[str]=[]; visual_goals:list[str]=[]; photo_retention_consent:bool=False
class LocalAuthIn(BaseModel):
    email:str;password:str
class WardrobeItemIn(BaseModel):
    category:str; subcategory:str; colors:list[str]; material_guess:list[str]=[]; material_confidence:float=Field(0,ge=0,le=1); pattern:str="纯色"; fit:str="常规"; length:str="常规"; wearing_layer:str="主上装"; warmth_level:int=Field(2,ge=0,le=5); formality_level:int=Field(2,ge=0,le=5); styles:list[str]=[]; seasons:list[str]=[]; weather_constraints:list[str]=[]; clean_status:WardrobeStatus="可穿"; image_url:str|None=None
class WardrobeItemOut(WardrobeItemIn):
    model_config=ConfigDict(from_attributes=True); id:str; user_id:str; image_asset_id:str|None=None; wear_count:int=0; last_worn_at:datetime|None=None
class UploadSignIn(BaseModel):
    filename:str;content_type:str;byte_size:int=Field(gt=0,le=12*1024*1024);kind:Literal["wardrobe","outfit_check","tryon"]="wardrobe"
class UploadCompleteIn(BaseModel):
    asset_id:str;category:str;subcategory:str;color:str;material_guess:list[str]=[];material_confidence:float=Field(0,ge=0,le=1);pattern:str="待确认";fit:str="常规";length:str="待确认";wearing_layer:str="主上装";warmth_level:int=Field(2,ge=0,le=5);formality_level:int=Field(3,ge=0,le=5);styles:list[str]=[];seasons:list[str]=["四季"];weather_constraints:list[str]=[];clean_status:WardrobeStatus="可穿"
class WeatherContext(BaseModel):
    city:str="香港"; district:str|None=None; temperature_c:float=29; feels_like_c:float=33; temperature_max_c:float|None=None; temperature_min_c:float|None=None; rain_probability:float=0.45; wind_level:float=3; condition:str="多云"
class OutfitRequest(BaseModel):
    occasion:str="商务休闲"; formality_level:int=3; indoor_ratio:float=.7; walking_minutes:int=30; mood:str="轻松"; mode:str="fast"; temporary_requirements:list[str]=[]; locked_item_ids:list[str]=[]; session_id:str|None=None; chat_history:list[dict]=[]; weather:WeatherContext=WeatherContext()
class OutfitResult(BaseModel):
    title:str; kind:str; item_ids:list[str]; reason:str; color_guide:str; wearing_tips:list[str]; alternative_item_ids:list[str]; scores:dict[str,float]; warnings:list[str]=[]; outfit_id:str|None=None; tryon_result_url:str|None=None
class OutfitResponse(BaseModel):
    request_id:str; outfits:list[OutfitResult]=Field(min_length=3,max_length=3); generated_by:str; preview_task_ids:list[str]=[]; intent_understanding:dict={}; evidence_pack:list[dict]=[]; answer_guard:dict={}
class FeedbackIn(BaseModel):
    outfit_id:str; adopted:bool; replace_today:bool=False; replaced_item_ids:list[str]=[]; feedback_tags:list[str]=[]; free_text:str|None=None
class ReplaceOutfitItemIn(BaseModel):
    outfit_id:str; item_id:str; mode:Literal["similar","different_color","different_style","remove","custom"]="similar"; replacement_item_id:str|None=None
class PhotoAnalysis(BaseModel):
    color:str; proportion:str; layering:str; accessories:str; weather_fit:str; actionable_tips:list[str]; prohibited_inferences:list[str]=[]; deleted_after_analysis:bool=True

class DayInput(BaseModel):
    date:str; occasion:str="日常通勤"; formality_level:int=3; weather:WeatherContext=WeatherContext(); notes:list[str]=[]
class WeeklyPlanRequest(BaseModel):
    start_date:str; days:list[DayInput]=Field(min_length=5,max_length=7); reuse_target:int=2; avoid_consecutive_repeat:bool=True
class DayPlan(BaseModel):
    date:str; occasion:str; item_ids:list[str]; weather:WeatherContext; reason:str; reuse_notes:list[str]=[]; warnings:list[str]=[]
class WeeklyPlanResult(BaseModel):
    plan_id:str; version:int; days:list[DayPlan]; capsule_item_ids:list[str]; laundry_windows:list[str]; color_story:list[str]
class ReplanRequest(BaseModel):
    changed_dates:list[str]; updates:dict[str,DayInput]; unavailable_item_ids:list[str]=[]
class GraphNode(BaseModel):
    item_id:str; label:str; category:str; core_score:float; isolated:bool=False
class GraphEdge(BaseModel):
    source:str; target:str; score:float; reasons:list[str]
class WardrobeGraphResult(BaseModel):
    nodes:list[GraphNode]; edges:list[GraphEdge]; isolated_item_ids:list[str]; core_item_ids:list[str]
class TravelPlanRequest(BaseModel):
    destination:str; start_date:str; end_date:str; days:list[DayInput]; laundry_available:bool=False; luggage_size:str="登机箱"; max_items:int=12
class TravelPlanResult(BaseModel):
    plan_id:str; destination:str; packing_item_ids:list[str]; daily_outfits:list[DayPlan]; reuse_map:dict[str,list[str]]; emergency_plan:list[str]; packing_order:list[str]; missing_items:list[str]
class SceneInput(BaseModel):
    name:str; time:str; occasion:str; formality_level:int; activity:str="步行较少"
class MultiSceneRequest(BaseModel):
    date:str; scenes:list[SceneInput]=Field(min_length=2,max_length=5); weather:WeatherContext=WeatherContext()
class MultiSceneResult(BaseModel):
    plan_id:str; base_item_ids:list[str]; transitions:list[dict]; carry_item_ids:list[str]; total_changes:int; explanation:str
class StyleIdentityResult(BaseModel):
    signature_colors:list[str]; silhouettes:list[str]; core_item_ids:list[str]; preferred_formality:float; exploration_range:dict; context_expressions:dict; evolution:list[dict]; confidence:float; narrative:str
class ProactiveEventIn(BaseModel):
    event_type:str; scheduled_for:datetime; importance:float=Field(ge=0,le=1); payload:dict; source_scope:str
class NotificationPreferencesIn(BaseModel):
    enabled:bool=True; important_events_only:bool=True; weather_change_threshold:float=5; reminder_time:str="20:30"; quiet_hours:str="22:00-07:30"; channels:list[str]=["in_app"]
class PurchaseCandidate(BaseModel):
    name:str; category:str; colors:list[str]; price:float|None=None; styles:list[str]=[]; material:str|None=None; image_url:str|None=None
class PurchaseResult(BaseModel):
    analysis_id:str; decision:str; duplication_score:float; compatibility_score:float; valid_outfit_count:int; resolves_gap:bool; best_color:str|None; matching_item_ids:list[str]; idle_risks:list[str]; size_questions:list[str]; explanation:str
class TryOnRequest(BaseModel):
    person_asset_id:str; outfit_id:str; views:list[str]=["front","side"]; outerwear_state:str="open"; preserve_identity:bool=True
class AdvancedPhotoAnalysis(PhotoAnalysis):
    strongest_issue:str; minimal_change:dict; enhanced_change:dict; before_after:list[dict]; change_cost:str; expected_effect:str; observations:list[dict]=[]; matched_wardrobe_item_ids:list[str]=[]; evidence_guard:dict={}
class BehaviorSignalIn(BaseModel):
    context_key:str; feature_key:str; value:float; source:str="explicit_action"; item_id:str|None=None
