<template>
  <div class="viz-page">
    <aside class="viz-sidebar">
      <h3>模型资源（模拟 /api/models/:id）</h3>
      <p class="viz-tip">演示：通过「模型 ID → 后端 API → 资源地址」加载 3DGS 模型</p>
      <button
        v-for="m in MOCK_MODEL_LIST"
        :key="m.id"
        class="viz-btn"
        :class="{ active: m.id === currentId }"
        :disabled="loading"
        @click="loadById(m.id)"
      >
        {{ m.name }}
      </button>
      <p v-if="currentPath" class="viz-path">资源地址：<br />{{ currentPath }}</p>
      <p v-if="error" class="viz-error">{{ error }}</p>

      <h3 style="margin-top: 18px">注入演示（useThreeDgsRenderer）</h3>
      <ModelStatsCard />
    </aside>
    <main class="viz-viewer">
      <ThreeDgsViewer ref="viewerRef" />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ThreeDgsViewer from '../components/ThreeDgsViewer.vue'
import ModelStatsCard from './ModelStatsCard.vue'
import { provideThreeDgsRenderer } from '../composables/useThreeDgsRenderer.js'

// —— 模拟后端 API 数据（卓奕臻的 /api/models/:id 就绪后替换为真实 fetch）——
// 约定字段：{ id, name, path, size }；与后端对齐的正式字段见 INTEGRATION.md
const MOCK_MODELS = {
  doll: { id: 'doll', name: '玩偶（老师提供）', path: '/models/export.ply', size: '36.8 MB' },
  'point-cloud': { id: 'point-cloud', name: '点云场景（老师提供）', path: '/models/point_cloud.ply', size: '141.9 MB' },
}
const MOCK_MODEL_LIST = Object.values(MOCK_MODELS)

const viewerRef = ref(null)
const currentId = ref('')
const currentPath = ref('')
const loading = ref(false)
const error = ref('')

// —— 契约第一步：建立注入通道（后代组件可用 useThreeDgsRenderer() 读取）——
const setRenderer = provideThreeDgsRenderer()

const fetchModelInfo = async (modelId) => {
  // TODO: 后端 API 就绪后改为：
  //   const res = await fetch(`/api/models/${modelId}`)
  //   if (!res.ok) throw new Error(`模型接口 ${res.status}`)
  //   return res.json()
  const model = MOCK_MODELS[modelId]
  if (!model) throw new Error('模型不存在：' + modelId)
  return model
}

const loadById = async (modelId) => {
  loading.value = true
  error.value = ''
  try {
    const model = await fetchModelInfo(modelId)
    currentId.value = model.id
    currentPath.value = model.path
    // —— 契约第二步：把 ThreeDgsViewer 暴露的渲染器实例写入注入通道 ——
    setRenderer(viewerRef.value.getRenderer())
    await viewerRef.value.loadModelByPath(model.path, model)
  } catch (err) {
    error.value = '加载失败：' + (err?.message || err)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.viz-page { display: flex; height: 100%; }
.viz-sidebar {
  width: 260px;
  padding: 16px;
  border-right: 1px solid #22303e;
  font-size: 13px;
  overflow-y: auto;
}
.viz-sidebar h3 { font-size: 14px; margin-bottom: 8px; }
.viz-tip { font-size: 12px; color: #8a99aa; margin-bottom: 10px; line-height: 1.6; }
.viz-btn {
  display: block;
  width: 100%;
  text-align: left;
  margin-bottom: 8px;
  font-size: 13px;
  color: #b9c9d8;
  background: rgba(10, 17, 24, 0.6);
  border: 1px solid #2a3b4d;
  border-radius: 6px;
  padding: 8px 12px;
  cursor: pointer;
}
.viz-btn:hover:not(:disabled) { border-color: #7fb3f0; color: #dbe7f3; }
.viz-btn.active { border-color: #7fb3f0; color: #7fb3f0; }
.viz-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.viz-path {
  margin-top: 10px;
  font-size: 11px;
  color: #7d93a8;
  word-break: break-all;
  line-height: 1.6;
}
.viz-error { margin-top: 10px; font-size: 12px; color: #fb8a91; }
.viz-viewer { flex: 1; min-width: 0; }
</style>
