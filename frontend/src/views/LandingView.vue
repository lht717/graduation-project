<script setup>
import { useAuthStore } from "@/stores/auth.js";
import AppLink from "@/components/AppLink.vue";

defineOptions({ name: "LandingView" });

const auth = useAuthStore();

function scrollToCapabilities() {
  document.querySelector("#capabilities").scrollIntoView({ behavior: "smooth" });
}
</script>

<template>
  <section id="landingView" class="landing-page">
    <header class="topbar landing-topbar">
      <AppLink class="brand" route="home" aria-label="FusionLab 首页">
        <div class="brand-mark" aria-hidden="true"></div>Fusion<span>Lab</span>
      </AppLink>
      <nav class="nav landing-nav" aria-label="主导航">
        <AppLink class="landing-nav-active" route="home">首页</AppLink>
        <AppLink route="dashboard">实验中心</AppLink>
        <AppLink route="profile">个人中心</AppLink>
      </nav>
      <button class="landing-login" id="openLogin" @click="auth.openLogin()">登录平台 <span>↗</span></button>
    </header>
    <main class="container landing-content">
      <section class="hero">
        <div class="hero-copy">
          <div class="eyebrow"><span class="landing-live-dot"></span> AI ENGINEERING · SIMULATION &amp; PHYSICAL</div>
          <h1>让 AI 算法在<span>工程场景</span><br>完成感知与控制闭环</h1>
          <p>FusionLab 面向人工智能工程实践，将 CARLA 仿真、AI 视觉算法、边缘计算与浏览器实验工作台整合在一起，支持从虚拟仿真逐步扩展到虚实结合实验。</p>
          <div class="hero-actions">
            <button class="btn btn-primary" id="heroEnter" @click="auth.openLogin()">开始探索 <span>→</span></button>
            <button class="btn btn-soft" id="scrollCapabilities" @click="scrollToCapabilities">了解平台 <span>↓</span></button>
          </div>
          <div class="hero-note">
            <span><b>CARLA</b> 虚拟场景</span>
            <span><b>UFLD + YOLO</b> AI 感知</span>
            <span><b>WebSocket</b> 实时数据</span>
          </div>
        </div>
        <div class="hero-visual">
          <div class="glow"></div>
          <div class="demo-window">
            <div class="demo-bar"><span class="demo-indicator"></span><b>智能视觉 · 实时检测</b><span class="demo-live">LIVE</span></div>
            <div class="demo-canvas">
              <div class="vision-grid"></div>
              <div class="vision-meta"><span>CAM 01</span><span>1280 × 720</span></div>
              <div class="detection-frame"></div>
              <div class="car"><i></i><b></b><span></span></div>
              <div class="detection-crosshair"></div>
              <div class="vision-coordinate">x: 482 &nbsp; y: 216</div>
            </div>
            <div class="demo-footer">
              <div><span>运行模式</span><b>虚拟仿真</b></div>
              <div><span>推理引擎</span><b>ONNX Runtime</b></div>
              <div><span>识别目标</span><b><i class="landing-live-dot"></i> 04 个</b></div>
            </div>
          </div>
          <div class="floating f1"><strong>感知状态</strong><small>车道线识别正常</small></div>
          <div class="floating f2"><strong>推理延迟</strong><small>18 ms · 实时</small></div>
        </div>
      </section>
      <section id="capabilities" class="section landing-capabilities">
        <div class="section-head">
          <div><div class="eyebrow">CORE CAPABILITIES</div><h2>从虚拟仿真走向虚实结合</h2></div>
          <p>复用 CARLA 与 AI 算法能力，在同一实验工作台中完成场景运行、感知分析与虚实结合实践。</p>
        </div>
        <div class="feature-grid">
          <article class="feature"><span class="landing-feature-index">01 / SIMULATION</span><div class="landing-feature-icon">⌘</div><b>CARLA 实时仿真</b><p>浏览器实时显示仿真画面，并可完成车辆创建、启动、停止和销毁。</p><span class="feature-tag">虚拟场景</span></article>
          <article class="feature"><span class="landing-feature-index">02 / PERCEPTION</span><div class="landing-feature-icon">◎</div><b>AI 感知结果</b><p>通过 UFLD 与 YOLO 完成车道线和目标检测，实时查看算法识别结果。</p><span class="feature-tag">UFLD + YOLO</span></article>
          <article class="feature"><span class="landing-feature-index">03 / WORKSPACE</span><div class="landing-feature-icon">▦</div><b>统一实验工作台</b><p>运行配置、双路画面、车辆状态与日志集中呈现，实验流程清晰直观。</p><span class="feature-tag">一站式实践</span></article>
        </div>
      </section>
      <section id="workflow" class="landing-workflow">
        <div class="landing-workflow-head"><div><div class="eyebrow">● WORKFLOW</div><h2>当前实验运行链路</h2></div><span>SIMULATION LOOP</span></div>
        <div class="landing-flow-steps">
          <div><span>01</span><b>CARLA</b><small>虚拟场景采集</small></div><i>→</i>
          <div><span>02</span><b>ONNX</b><small>本地 AI 推理</small></div><i>→</i>
          <div><span>03</span><b>WebSocket</b><small>实时数据传输</small></div><i>→</i>
          <div><span>04</span><b>浏览器</b><small>结果可视化</small></div>
        </div>
        <p>后续可在虚实结合模式下，将算法执行节点切换至真实边缘计算设备。</p>
      </section>
      <section class="landing-cta">
        <p>准备好开始你的下一次实验了吗？</p>
        <button class="btn btn-primary" @click="auth.openLogin()">进入实验室 <span>→</span></button>
      </section>
    </main>
    <footer class="landing-footer">
      <span class="landing-footer-brand">Fusion Lab</span>
      <span>以实践连接算法，让智能走进真实场景。</span>
      <small>© 2026 AI Practice Lab</small>
    </footer>
  </section>
</template>
