export type WeatherDistrict={name:string;latitude:number;longitude:number};
export type WeatherCity={name:string;districts:WeatherDistrict[]};
export type WeatherProvince={name:string;cities:WeatherCity[]};
export type WeatherLocation={province:string;city:string;district:string;latitude:number;longitude:number};

export const WEATHER_LOCATIONS:WeatherProvince[]=[
  {name:"广东省",cities:[
    {name:"深圳市",districts:[{name:"福田区",latitude:22.5410,longitude:114.0558},{name:"罗湖区",latitude:22.5484,longitude:114.1317},{name:"南山区",latitude:22.5333,longitude:113.9304},{name:"盐田区",latitude:22.5570,longitude:114.2369},{name:"宝安区",latitude:22.5538,longitude:113.8831},{name:"龙岗区",latitude:22.7209,longitude:114.2469},{name:"龙华区",latitude:22.6967,longitude:114.0446},{name:"坪山区",latitude:22.6908,longitude:114.3463},{name:"光明区",latitude:22.7489,longitude:113.9359},{name:"大鹏新区",latitude:22.5969,longitude:114.4799}]},
    {name:"广州市",districts:[{name:"天河区",latitude:23.1246,longitude:113.3612},{name:"越秀区",latitude:23.1290,longitude:113.2668},{name:"海珠区",latitude:23.0833,longitude:113.3172},{name:"荔湾区",latitude:23.1259,longitude:113.2443},{name:"白云区",latitude:23.1579,longitude:113.2732},{name:"番禺区",latitude:22.9377,longitude:113.3841},{name:"黄埔区",latitude:23.1064,longitude:113.4597}]},
  ]},
  {name:"上海市",cities:[{name:"上海市",districts:[{name:"黄浦区",latitude:31.2316,longitude:121.4844},{name:"徐汇区",latitude:31.1883,longitude:121.4368},{name:"长宁区",latitude:31.2205,longitude:121.4246},{name:"静安区",latitude:31.2290,longitude:121.4484},{name:"浦东新区",latitude:31.2215,longitude:121.5447},{name:"闵行区",latitude:31.1133,longitude:121.3817},{name:"宝山区",latitude:31.4053,longitude:121.4896},{name:"松江区",latitude:31.0322,longitude:121.2277}]}]},
  {name:"北京市",cities:[{name:"北京市",districts:[{name:"东城区",latitude:39.9288,longitude:116.4160},{name:"西城区",latitude:39.9123,longitude:116.3659},{name:"朝阳区",latitude:39.9219,longitude:116.4436},{name:"海淀区",latitude:39.9593,longitude:116.2981},{name:"丰台区",latitude:39.8585,longitude:116.2867},{name:"通州区",latitude:39.9099,longitude:116.6564}]}]},
];

export const DEFAULT_WEATHER_LOCATION:WeatherLocation={province:"广东省",city:"深圳市",district:"南山区",latitude:22.5333,longitude:113.9304};
export const DEFAULT_WEATHER_CITY=DEFAULT_WEATHER_LOCATION.city;
const WEATHER_LOCATION_KEY="ootd.weather_location";

export function readWeatherLocation():WeatherLocation{if(typeof window==="undefined")return DEFAULT_WEATHER_LOCATION;try{return {...DEFAULT_WEATHER_LOCATION,...JSON.parse(localStorage.getItem(WEATHER_LOCATION_KEY)||"")}}catch{return DEFAULT_WEATHER_LOCATION}}
export function saveWeatherLocation(value:WeatherLocation){if(typeof window!=="undefined")localStorage.setItem(WEATHER_LOCATION_KEY,JSON.stringify(value));return value}
export const readWeatherCity=()=>readWeatherLocation().city;
export const saveWeatherCity=(city:string)=>city.trim();
