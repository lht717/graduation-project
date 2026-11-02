import { config } from "../config.js";
import { installMock } from "./mock.js";

installMock(config.useMock);

export async function request(path, options = {}) {
  const isModelRequest = new URL(path, window.location.href).pathname.startsWith("/api/models");
  const requestUrl = isModelRequest
    ? new URL(path, `${config.apiBaseUrl.replace(/\/$/, "")}/`).href
    : path;
  const response = await fetch(requestUrl, {
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {})
    }
  });
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      throw new Error("服务器返回的数据格式无效");
    }
  }
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `请求失败（HTTP ${response.status}）`);
  }
  return payload;
}

export function get(path, options) {
  return request(path, { method: "GET", ...options });
}

export function post(path, body, options) {
  const isBody = body instanceof Blob || body instanceof FormData;
  return request(path, {
    ...options,
    method: "POST",
    headers: {
      ...(isBody ? {} : { "Content-Type": "application/json" }),
      ...(options?.headers || {})
    },
    body: isBody ? body : JSON.stringify(body || {})
  });
}

export function put(path, body, options) {
  return request(path, {
    ...options,
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {})
    },
    body: JSON.stringify(body || {})
  });
}

export function patch(path, body, options) {
  return request(path, {
    ...options,
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {})
    },
    body: JSON.stringify(body || {})
  });
}

export function remove(path, options = {}) {
  return request(path, { ...options, method: "DELETE" });
}
