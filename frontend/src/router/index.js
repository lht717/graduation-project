import { createRouter as createVueRouter } from "vue-router";
import { createLegacyHashHistory } from "./hashHistory";
import { useAuthStore } from "@/stores/auth";
import LandingView from "@/views/LandingView.vue";
import DashboardView from "@/views/DashboardView.vue";
import WorkspaceView from "@/views/WorkspaceView.vue";
import ProfileView from "@/views/ProfileView.vue";
import MessageView from "@/views/MessageView.vue";
import AdminView from "@/views/AdminView.vue";

// 与原版 routes 集合一一对应
export const ROUTE_NAMES = ["home", "dashboard", "workspace", "profile", "message", "admin"];

const routes = [
  { path: "/", redirect: "/home" },
  { path: "/home", name: "home", component: LandingView },
  { path: "/dashboard", name: "dashboard", component: DashboardView, meta: { requiresAuth: true } },
  { path: "/workspace", name: "workspace", component: WorkspaceView, meta: { requiresAuth: true } },
  { path: "/profile", name: "profile", component: ProfileView, meta: { requiresAuth: true } },
  { path: "/message", name: "message", component: MessageView, meta: { requiresAuth: true } },
  { path: "/admin", name: "admin", component: AdminView, meta: { requiresAuth: true, requiresAdmin: true } },
  { path: "/:pathMatch(.*)*", redirect: "/home" }
];

/** 复刻原版 routeFromLocation() */
export function resolveInitialRoute() {
  const hashRoute = window.location.hash.slice(1);
  if (ROUTE_NAMES.includes(hashRoute)) return hashRoute;
  if (new URLSearchParams(window.location.search).get("view") === "dashboard") return "dashboard";
  return "home";
}

export function createRouter() {
  const router = createVueRouter({
    history: createLegacyHashHistory(),
    routes
  });

  // 复刻原版 showView() 的两道守卫：先登录，再管理员
  router.beforeEach((to) => {
    const auth = useAuthStore();
    if (to.meta.requiresAuth && !auth.authenticated) {
      auth.openLogin("请先登录后访问该页面。");
      return { path: "/home", replace: true };
    }
    if (to.meta.requiresAdmin && auth.user.role !== "admin") {
      return { path: "/dashboard", replace: true };
    }
    return true;
  });

  // 原版 showView() 在视图切换成功后调用 closeLogin()
  router.afterEach(() => {
    useAuthStore().closeLogin();
  });

  return router;
}
