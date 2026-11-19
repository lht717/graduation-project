<template>
  <div class="page">
    <header class="page-head">
      <h1>3DGS 可视化渲染器</h1>
      <p>
        基于 Three.js 与 3DGS 模型的可视化前端 · ThreeDgsRenderer
        <span v-if="showViz"> · 当前为平台页集成参考实现（VisualizationView）</span>
      </p>
    </header>
    <main class="page-body">
      <VisualizationView v-if="showViz" />
      <ThreeDgsViewer v-else />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ThreeDgsViewer from './components/ThreeDgsViewer.vue'
import VisualizationView from './reference/VisualizationView.vue'

// 演示入口切换：URL 加 #viz 展示平台页集成参考实现（第 9 步契约演示）
const showViz = ref(window.location.hash.includes('viz'))
</script>

<style>
/* 基础样式，后续步骤逐步完善 */
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
body {
  font-family: system-ui, -apple-system, "Microsoft YaHei", sans-serif;
  background: #0f1720;
  color: #e6edf3;
}
.page { height: 100%; display: flex; flex-direction: column; }
.page-head { padding: 14px 20px; border-bottom: 1px solid #22303e; }
.page-head h1 { font-size: 18px; }
.page-head p { font-size: 12px; color: #8a99aa; margin-top: 4px; }
.page-body { flex: 1; min-height: 0; }
</style>
