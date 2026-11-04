import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { createRouter, resolveInitialRoute } from "@/router/index.js";
import { useAuthStore } from "@/stores/auth.js";
import "@/assets/styles/app.css";

async function bootstrap() {
  const app = createApp(App);
  const pinia = createPinia();
  app.use(pinia);

  const auth = useAuthStore(pinia);
  // 原版 routeFromLocation() 在导航前就把「用户想去哪」定下来了
  const intent = resolveInitialRoute();

  // 原版 initialize()：先拿 /api/auth/me，再决定落地视图
  await auth.bootstrap();

  const router = createRouter();
  app.use(router);
  await router.isReady();

  // 原版：initialRoute !== home 且未登录 → 先回到 home，再弹登录框
  if (intent !== "home" && !auth.authenticated) {
    auth.openLogin("请先登录后访问该页面。");
  }
  if (new URLSearchParams(window.location.search).get("openLogin") === "1") auth.openLogin();

  app.mount("#app");
}

void bootstrap();
