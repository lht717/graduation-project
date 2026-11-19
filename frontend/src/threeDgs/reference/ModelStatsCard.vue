<template>
  <div class="stats-card">
    <p v-if="!rendererRef">渲染器未注入（祖先组件尚未调用 provideThreeDgsRenderer 的 setter）</p>
    <template v-else>
      <p v-if="!rendererRef.value">渲染器已注入，等待模型加载…</p>
      <template v-else>
        <p>泼溅点数：<strong>{{ splatCount.toLocaleString() }}</strong></p>
        <p>渲染后端：<strong>{{ caps.backend.toUpperCase() }}</strong></p>
        <p>WebGPU：<strong>{{ caps.webgpuSupported ? '可用' : '不可用' }}</strong></p>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, watchEffect } from 'vue'
import { useThreeDgsRenderer } from '../composables/useThreeDgsRenderer.js'

// —— 契约第三步：后代组件注入渲染器（与祖先零耦合，只依赖注入 key）——
const rendererRef = useThreeDgsRenderer()

// 每次渲染后重新读取渲染器状态（模型信息会随加载/切换变化）
const splatCount = computed(() => rendererRef?.value?.getModelInfo()?.splatCount ?? 0)
const caps = computed(() => rendererRef?.value?.getCapabilities?.() ?? { backend: 'webgl2', webgpuSupported: false })
watchEffect(() => { rendererRef?.value }) // 依赖渲染器引用本身，保证响应式
</script>

<style scoped>
.stats-card {
  font-size: 12px;
  color: #b9c9d8;
  background: rgba(10, 17, 24, 0.6);
  border: 1px solid #2a3b4d;
  border-radius: 6px;
  padding: 10px 12px;
  line-height: 1.9;
}
.stats-card strong { color: #7fb3f0; }
</style>
