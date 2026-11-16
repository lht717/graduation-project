// API / WebSocket 地址：默认跟随页面来源（window.location），
// 即"从哪台机器的浏览器打开，就请求哪台机器的后端"——
// 局域网内任何电脑访问都不需要再手改 IP。
// 如需固定后端地址，可在 frontend/.env.local 里设置 VITE_API_BASE，例如：
//   VITE_API_BASE=http://192.168.1.23:8080
const envBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const origin = window.location.origin; // 例如 http://192.168.55.100:8080
const wsProto = origin.startsWith("https") ? "wss" : "ws";

export const config = Object.freeze({
  apiBaseUrl: envBase || origin,
  wsUrl: `${wsProto}://${window.location.host}/ws`
});
