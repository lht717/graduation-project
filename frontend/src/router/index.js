import { createRouter as createVueRouter } from "vue-router";
import { createLegacyHashHistory } from "./hashHistory";
import { useAuthStore } from "@/stores/auth";
import LandingView from "@/views/LandingView.vue";
import DashboardView from "@/views/DashboardView.vue";
import WorkspaceView from "@/views/WorkspaceView.vue";
import ProfileView from "@/views/ProfileView.vue";
import MessageView from "@/views/MessageView.vue";
import AdminView from "@/views/AdminView.vue";
import VisualizationView from "@/threeDgs/reference/VisualizationView.vue";

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
  // 3D 可视化页（viewer 集成）。
  // 注意：录制演示阶段临时去掉 requiresAuth 以便直接访问；
  // 答辩演示（后端就绪）时恢复 meta: { requiresAuth: true } 展示完整登录流。
  { path: "/visualization", name: "visualization", component: VisualizationView },
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

  // 被登录守卫拦截的导航：跳回首页后要保持登录弹窗打开（否则 afterEach 会立刻关掉）
  let promptLoginAfterRedirect = false;

  // 复刻原版 showView() 的两道守卫：先登录，再管理员
  router.beforeEach((to) => {
    const auth = useAuthStore();
    if (to.meta.requiresAuth && !auth.authenticated) {
      // 记住用户原本想访问的页面，登录成功后直接跳过去
      auth.loginRedirect = to.fullPath;
      promptLoginAfterRedirect = true;
      return { path: "/home", replace: true };
    }
    if (to.meta.requiresAdmin && auth.user.role !== "admin") {
      return { path: "/dashboard", replace: true };
    }
    return true;
  });

  // 原版 showView() 在正常的视图切换后调用 closeLogin()
  router.afterEach(() => {
    const auth = useAuthStore();
    if (promptLoginAfterRedirect) {
      // 未登录点「实验中心 / 个人中心」等受保护入口：直接展示登录界面并保持打开
      promptLoginAfterRedirect = false;
      auth.openLogin("请先登录后访问该页面。");
      return;
    }
    auth.closeLogin();
  });

  return router;
}
