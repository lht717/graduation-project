<template>
  <div ref="container" class="viewer" @pointerdown.once="showHints = false">
    <!-- 模型选择栏 -->
    <div class="viewer-toolbar">
      <button
        v-for="model in MODELS"
        :key="model.id"
        class="model-tab"
        :class="{ active: model.id === currentModelId }"
        :disabled="loading"
        @click="loadModel(model)"
      >
        {{ model.name }}
      </button>
      <span class="toolbar-divider"></span>
      <button
        v-for="gltf in GLTF_MODELS"
        :key="gltf.id"
        class="model-tab gltf-tab"
        :class="{ active: gltfState.loaded.has(gltf.id) }"
        :disabled="loading || gltfState.loading.has(gltf.id)"
        :title="gltfState.loaded.has(gltf.id) ? '点击移除该 glTF 模型' : '叠加 glTF 网格模型（与 3DGS 共存）'"
        @click="toggleGLTF(gltf)"
      >
        {{ gltfLabel(gltf) }}
      </button>
    </div>

    <!-- 加载进度 -->
    <div v-if="loading" class="viewer-status">
      <span class="spinner"></span>
      <div class="status-body">
        <div class="status-text">{{ loadingText }}</div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: progress + '%' }"></div>
        </div>
      </div>
    </div>

    <!-- 加载失败 -->
    <div v-else-if="error" class="viewer-status">
      <span class="status-icon">✕</span>
      <div class="status-body">
        <div class="status-text">{{ error }}</div>
        <button class="retry-btn" @click="loadModel(currentModel)">重试</button>
      </div>
    </div>

    <!-- 信息面板 -->
    <div v-if="!loading && !error && modelInfo" class="viewer-panel">
      <div class="panel-title">模型信息</div>
      <dl class="panel-kv">
        <dt>名称</dt>
        <dd>{{ currentModel.name }}</dd>
        <dt>文件大小</dt>
        <dd>{{ currentModel.size }}</dd>
        <dt>点数</dt>
        <dd>{{ modelInfo.splatCount.toLocaleString() }}</dd>
        <dt>包围盒</dt>
        <dd>{{ boxSizeText }}</dd>
      </dl>
      <div class="panel-divider"></div>
      <div class="panel-title">渲染能力</div>
      <dl v-if="caps" class="panel-kv">
        <dt>后端</dt>
        <dd>{{ caps.backend.toUpperCase() }}</dd>
        <dt>WebGPU</dt>
        <dd>{{ caps.webgpuSupported ? '可用（预留）' : '不可用' }}</dd>
        <dt>跨源隔离</dt>
        <dd>{{ caps.crossOriginIsolated ? '已启用' : '未启用' }}</dd>
      </dl>
      <div class="panel-divider"></div>
      <div class="panel-title">拾取点</div>
      <template v-if="picked">
        <dl class="panel-kv">
          <dt>X</dt>
          <dd>{{ picked.x.toFixed(3) }}</dd>
          <dt>Y</dt>
          <dd>{{ picked.y.toFixed(3) }}</dd>
          <dt>Z</dt>
          <dd>{{ picked.z.toFixed(3) }}</dd>
          <dt>相机距离</dt>
          <dd>{{ picked.distance.toFixed(3) }}</dd>
        </dl>
        <button class="panel-clear" @click="clearPick">清空标记</button>
      </template>
      <p v-else class="panel-empty">单击模型上的任意点，此处显示该点的世界坐标</p>
    </div>

    <!-- glTF 调整面板（加载 glTF 后显示） -->
    <div v-if="gltfState.loaded.size > 0" class="gltf-adjust">
      <div class="panel-title">glTF 调整 <span class="adjust-hint">（Y 轴向下）</span></div>
      <div class="adjust-row">
        <span class="adjust-label">X</span>
        <input type="range" min="-5" max="5" step="0.01" v-model.number="gltfPos.x" @input="applyGLTFTransform" @change="refitCamera" />
        <span class="adjust-value">{{ gltfPos.x.toFixed(2) }}</span>
      </div>
      <div class="adjust-row">
        <span class="adjust-label">Y</span>
        <input type="range" min="-5" max="5" step="0.01" v-model.number="gltfPos.y" @input="applyGLTFTransform" @change="refitCamera" />
        <span class="adjust-value">{{ gltfPos.y.toFixed(2) }}</span>
      </div>
      <div class="adjust-row">
        <span class="adjust-label">Z</span>
        <input type="range" min="-5" max="5" step="0.01" v-model.number="gltfPos.z" @input="applyGLTFTransform" @change="refitCamera" />
        <span class="adjust-value">{{ gltfPos.z.toFixed(2) }}</span>
      </div>
      <div class="adjust-row">
        <span class="adjust-label">大小</span>
        <input type="range" min="0.05" max="5" step="0.01" v-model.number="gltfScale" @input="applyGLTFTransform" @change="refitCamera" />
        <span class="adjust-value">{{ gltfScale.toFixed(2) }}</span>
      </div>
      <button class="panel-clear" @click="resetGLTFTransform">复位为默认值</button>
    </div>

    <!-- 操作提示 -->
    <div v-if="showHints && !loading && !error" class="viewer-hints">
      左键拖动旋转 · 滚轮缩放 · 右键平移 · 双击复位 · 单击拾取坐标
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ThreeDgsRenderer } from '../renderer/ThreeDgsRenderer.js'
import { GLTF_MODELS, MODELS } from '../config/models.js'

const container = ref(null)
const currentModelId = ref(MODELS[0].id)
const loading = ref(false)
const progress = ref(0)
const error = ref('')
const showHints = ref(true)
const modelInfo = ref(null)
const picked = ref(null) // { x, y, z, distance } 拾取点信息（世界坐标）
const caps = ref(null) // 渲染能力（WebGL2 后端 / WebGPU 检测 / 跨源隔离，第 8 步）
// glTF 叠加状态：loaded = 已加载的模型 id 集合，loading = 加载中的模型 id 集合
const gltfState = reactive({ loaded: new Set(), loading: new Set() })
// glTF 调整面板状态（当前只支持调整第一个加载的 glTF，与 GLTF_MODELS 顺序一致）
const gltfPos = reactive({ x: 0, y: 0, z: 0 })
const gltfScale = ref(1)
let activeGLTFModel = null

let renderer = null

const currentModel = computed(() => MODELS.find((m) => m.id === currentModelId.value))

const gltfLabel = (gltf) => {
  if (gltfState.loading.has(gltf.id)) return 'glTF 加载中…'
  return (gltfState.loaded.has(gltf.id) ? '✓ ' : '＋ ') + gltf.name
}

const applyGLTFTransform = () => {
  renderer.setGLTFTransform(activeGLTFModel, {
    position: [gltfPos.x, gltfPos.y, gltfPos.z],
    scale: gltfScale.value, // 注意必须是 .value，Ref 对象参与矩阵运算会变 NaN 导致模型消失
  })
}

// 滑杆松手后重新取景，保证调整过程中跑车不会"跑出画面"
const refitCamera = () => renderer.fitToModel()

// 复位为配置文件里的默认值；配置未指定位置时重新自动摆放到泼溅模型旁边
const resetGLTFTransform = () => {
  const gltf = GLTF_MODELS.find((g) => gltfState.loaded.has(g.id))
  if (!gltf || !activeGLTFModel) return
  if (gltf.position) {
    gltfPos.x = gltf.position[0]
    gltfPos.y = gltf.position[1]
    gltfPos.z = gltf.position[2]
  } else {
    renderer.autoPlaceGLTF(activeGLTFModel)
    gltfPos.x = activeGLTFModel.position.x
    gltfPos.y = activeGLTFModel.position.y
    gltfPos.z = activeGLTFModel.position.z
  }
  gltfScale.value = gltf.scale ?? 1
  applyGLTFTransform()
  refitCamera()
}

const loadingText = computed(() => {
  const model = currentModel.value
  if (progress.value >= 100) {
    return `下载完成，正在构建 ${model ? model.name : '模型'}…`
  }
  return `正在加载 ${model ? model.name : '模型'}（${progress.value.toFixed(0)}%）…`
})

const boxSizeText = computed(() => {
  const s = modelInfo.value?.size
  return s ? `${s.x.toFixed(2)} × ${s.y.toFixed(2)} × ${s.z.toFixed(2)}` : ''
})

const loadModel = async (model) => {
  currentModelId.value = model.id
  loading.value = true
  error.value = ''
  progress.value = 0
  picked.value = null // 切换模型后旧拾取点已无意义
  try {
    await renderer.unloadCurrentSplat()
    await renderer.loadSplat(model.path, {
      progressive: model.progressive,
      onProgress: (percent) => {
        progress.value = percent
      },
    })
    modelInfo.value = renderer.getModelInfo()
  } catch (err) {
    error.value = '模型加载失败：' + (err?.message || err)
  } finally {
    loading.value = false
  }
}

// 平台页接入接口（第 9 步）：按模型 URL 加载（走内部加载进度/失败 UI 流程），
// 供 VisualizationView 从后端 API 拿到资源地址后调用
const loadModelByPath = async (path, meta = {}) => {
  return loadModel({
    id: meta.id ?? 'external',
    name: meta.name ?? '外部模型',
    path,
    size: meta.size ?? '',
    progressive: meta.progressive ?? true,
  })
}

// 对父组件暴露的集成接口（第 9 步契约，与 INTEGRATION.md 一致）
defineExpose({
  /** 获取渲染器实例（配合 provideThreeDgsRenderer 注入给后代组件） */
  getRenderer: () => renderer,
  /** 按模型资源地址加载（模型信息来自后端 API 时使用） */
  loadModelByPath,
})

const clearPick = () => {
  picked.value = null
  renderer.clearPickMarker()
}

// 切换 glTF 模型：未加载则叠加进场景，已加载则移除（切换 3DGS 模型时 glTF 保持叠加）
const toggleGLTF = async (gltf) => {
  if (gltfState.loaded.has(gltf.id)) {
    renderer.unloadGLTF()
    gltfState.loaded.clear()
    activeGLTFModel = null
    return
  }
  gltfState.loading.add(gltf.id)
  try {
    const model = await renderer.loadGLTF(gltf.path, {
      flipY: gltf.flipY,
      position: gltf.position,
      scale: gltf.scale,
    })
    activeGLTFModel = model
    // 配置里指定了位置则回显，否则回显自动摆放后的实际位置
    gltfPos.x = gltf.position?.[0] ?? model.position.x
    gltfPos.y = gltf.position?.[1] ?? model.position.y
    gltfPos.z = gltf.position?.[2] ?? model.position.z
    gltfScale.value = gltf.scale ?? 1
    gltfState.loaded.add(gltf.id)
  } catch (err) {
    error.value = 'glTF 加载失败：' + (err?.message || err)
  } finally {
    gltfState.loading.delete(gltf.id)
  }
}

onMounted(async () => {
  renderer = new ThreeDgsRenderer(container.value)
  caps.value = renderer.getCapabilities()
  // 点击拾取回调：命中时携带世界坐标，落空（点到空白处）时为 null
  renderer.onPick = (hit) => {
    picked.value = hit
      ? { x: hit.position.x, y: hit.position.y, z: hit.position.z, distance: hit.distance }
      : null
  }
  renderer.start()
  await loadModel(MODELS[0])
})

onBeforeUnmount(() => {
  if (renderer) {
    renderer.dispose()
    renderer = null
  }
})
</script>

<style scoped>
.viewer {
  height: 100%;
  position: relative;
  overflow: hidden;
  background: #0a1118;
}
.viewer-toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 8px;
  z-index: 10;
}
.model-tab {
  font-size: 13px;
  color: #b9c9d8;
  background: rgba(10, 17, 24, 0.82);
  border: 1px solid #2a3b4d;
  border-radius: 6px;
  padding: 7px 14px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.model-tab:hover:not(:disabled) {
  border-color: #7fb3f0;
  color: #dbe7f3;
}
.model-tab.active {
  border-color: #7fb3f0;
  color: #7fb3f0;
}
.model-tab:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.toolbar-divider {
  width: 1px;
  height: 22px;
  background: #2a3b4d;
  align-self: center;
  margin: 0 2px;
}
.gltf-tab {
  color: #9fc4a9;
}
.gltf-adjust {
  position: absolute;
  bottom: 14px;
  left: 12px;
  width: 224px;
  font-size: 12px;
  color: #b9c9d8;
  background: rgba(10, 17, 24, 0.82);
  border: 1px solid #2a3b4d;
  border-radius: 8px;
  padding: 12px 14px;
  z-index: 10;
}
.adjust-hint {
  color: #7d93a8;
  font-size: 11px;
  font-weight: 400;
}
.adjust-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 9px;
}
.adjust-label {
  width: 14px;
  color: #7d93a8;
}
.adjust-row input[type='range'] {
  flex: 1;
  min-width: 0;
  accent-color: #7fb3f0;
}
.adjust-value {
  width: 38px;
  text-align: right;
  color: #9fc4a9;
  font-variant-numeric: tabular-nums;
}
.viewer-panel {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 232px;
  font-size: 12px;
  color: #b9c9d8;
  background: rgba(10, 17, 24, 0.82);
  border: 1px solid #2a3b4d;
  border-radius: 8px;
  padding: 12px 14px;
  z-index: 10;
}
.panel-title {
  font-weight: 600;
  color: #7fb3f0;
  margin-bottom: 8px;
}
.panel-kv {
  margin: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
}
.panel-kv dt {
  color: #7d93a8;
}
.panel-kv dd {
  margin: 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.panel-divider {
  height: 1px;
  background: #2a3b4d;
  margin: 12px 0;
}
.panel-empty {
  margin: 0;
  color: #7d93a8;
  line-height: 1.6;
}
.panel-clear {
  margin-top: 10px;
  font-size: 12px;
  color: #7fb3f0;
  background: none;
  border: 1px solid #3a5066;
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
}
.panel-clear:hover {
  border-color: #7fb3f0;
}
.viewer-status {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 13px;
  color: #b9c9d8;
  background: rgba(10, 17, 24, 0.82);
  border: 1px solid #2a3b4d;
  border-radius: 8px;
  padding: 12px 20px;
  pointer-events: none;
  z-index: 10;
}
.status-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: auto;
}
.status-text {
  font-size: 13px;
  color: #b9c9d8;
}
.progress-track {
  width: 220px;
  height: 6px;
  background: #1c2a38;
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: #7fb3f0;
  border-radius: 3px;
  transition: width 0.15s ease;
}
.retry-btn {
  align-self: flex-start;
  font-size: 12px;
  color: #7fb3f0;
  background: none;
  border: 1px solid #3a5066;
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
}
.retry-btn:hover {
  border-color: #7fb3f0;
}
.spinner {
  width: 13px;
  height: 13px;
  border: 2px solid #3a5066;
  border-top-color: #7fb3f0;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.status-icon {
  color: #fb8a91;
  font-weight: 700;
}
.viewer-hints {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 12px;
  color: #9fb3c8;
  background: rgba(10, 17, 24, 0.7);
  border: 1px solid #2a3b4d;
  border-radius: 999px;
  padding: 6px 14px;
  white-space: nowrap;
  pointer-events: none;
  z-index: 10;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
