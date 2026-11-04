// 原版地址栏是 #dashboard / #profile 这种「一级 hash」形式。
// vue-router 自带的 hash 模式会写成 #/dashboard，为了让地址栏、前进后退、
// 刷新后的行为与原版逐字一致，这里实现一个最小的 RouterHistory：
//   - location 对外表现为 "/dashboard"
//   - 真实地址栏始终写 "#dashboard"
//   - push / replace 走 history.pushState / replaceState（与原型 navigate 相同）
//
// 注意：listen 的回调必须按 vue-router 的约定带上 (to, from, info)，
// 其中 info.delta / info.type 会被 finalizeNavigation 使用，缺了会抛 TypeError。

function toRouterPath(hash) {
  const raw = String(hash || "").replace(/^#/, "");
  if (!raw) return "/home";
  return raw.startsWith("/") ? raw : `/${raw}`;
}

function toLegacyHash(path) {
  const normalized = String(path || "/home").split("?")[0];
  const trimmed = normalized.replace(/^\/+/, "");
  return trimmed ? `#${trimmed}` : "#home";
}

function normalizeTarget(to) {
  if (typeof to === "string") return to;
  return (to && to.path) || "/home";
}

export function createLegacyHashHistory() {
  const listeners = new Set();
  let lastPath = toRouterPath(window.location.hash);

  function emitNavigation() {
    const to = toRouterPath(window.location.hash);
    if (to === lastPath) return;
    const from = lastPath;
    lastPath = to;
    // 原版只区分「进了哪个视图」，不区分前进后退方向
    const info = { delta: 0, type: "pop", direction: "" };
    for (const listener of [...listeners]) listener(to, from, info);
  }

  window.addEventListener("popstate", emitNavigation);
  window.addEventListener("hashchange", (event) => {
    if (event.newURL === event.oldURL) return;
    emitNavigation();
  });

  return {
    get base() {
      return "";
    },
    get location() {
      return toRouterPath(window.location.hash);
    },
    get state() {
      const state = window.history.state;
      return state && typeof state === "object" ? state : {};
    },
    createHref(to) {
      return toLegacyHash(normalizeTarget(to));
    },
    push(to) {
      const hash = toLegacyHash(normalizeTarget(to));
      // 与原版 navigate 一致：目标相同时不重复写历史
      if (window.location.hash !== hash) window.history.pushState(null, "", hash);
      lastPath = toRouterPath(window.location.hash);
    },
    replace(to) {
      const hash = toLegacyHash(normalizeTarget(to));
      window.history.replaceState(null, "", hash);
      lastPath = toRouterPath(window.location.hash);
    },
    go(delta) {
      window.history.go(delta);
    },
    listen(callback) {
      listeners.add(callback);
      return () => {
        listeners.delete(callback);
      };
    }
  };
}
