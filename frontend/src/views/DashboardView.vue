<script setup>
import { useRouter } from "vue-router";

defineOptions({ name: "DashboardView" });

const router = useRouter();

function openExperiment() {
  router.push("/workspace");
}
</script>

<template>
  <section id="dashboardView">
    <main class="container"><div class="dashboard-head"><div><div class="eyebrow">MY EXPERIMENTS</div><h1>我的实验</h1><p>选择一个实验进入工作台。实验工作台支持虚拟仿真与虚实结合两种运行模式。</p></div></div>
      <div class="experiment-grid">
        <article class="exp-card active-card"><div class="exp-art city"><span class="exp-badge">可运行 · 双模式</span></div><div class="exp-body"><h3>智能汽车视觉感知实验</h3><p>CARLA 城市道路 · UFLD 车道线检测 · YOLO 目标检测 · 自动驾驶状态监控</p><div class="exp-meta"><span class="chip">CARLA</span><span class="chip">ONNX Runtime</span><span class="chip">WebSocket</span></div><button class="btn btn-primary" id="openExperiment" @click="openExperiment">进入实验</button></div></article>
        <article class="exp-card coming"><div class="exp-art"><span class="exp-badge">规划中</span></div><div class="exp-body"><h3>仓储 AGV 实验</h3><p>将在后续场景适配阶段开放。</p><div class="exp-meta"><span class="chip">AGV</span><span class="chip">Warehouse</span></div><button class="btn btn-outline" disabled>暂未开放</button></div></article>
        <article class="exp-card coming"><div class="exp-art"><span class="exp-badge">规划中</span></div><div class="exp-body"><h3>巡检机器人实验</h3><p>将在机器人仿真适配完成后开放。</p><div class="exp-meta"><span class="chip">Robot</span><span class="chip">Patrol</span></div><button class="btn btn-outline" disabled>暂未开放</button></div></article>
      </div>
    </main>
  </section>
</template>
