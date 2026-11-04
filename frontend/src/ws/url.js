import { config } from "@/config.js";

export function resolveWsUrl() {
  if (config.wsUrl) return config.wsUrl;
  const apiUrl = new URL(config.apiBaseUrl || window.location.origin);
  apiUrl.protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  apiUrl.pathname = "/ws";
  apiUrl.search = "";
  apiUrl.hash = "";
  return apiUrl.href;
}
