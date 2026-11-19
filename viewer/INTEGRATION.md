# 3DGS 渲染器集成对接文档（给平台前端 · 林晶晶）

> 版本：2026-11-19 · 作者：李宏韬（viewer 部分） · 对接人：林晶晶（平台前端 fusionlab-frontend）

## 1. 仓库现状（重要）

协作仓库 `lht717/graduation-project` 当前三个分支：

| 分支 | 内容 | 说明 |
|------|------|------|
| `main` | 旧版 `static/` 原生 JS 前端 | ⚠️ 落后 linjingjing 15 个提交，无 Vue 前端 |
| `linjingjing` | Vue 前端 `frontend/` + 全部后端 | ✅ 最新，建议以它为准 |
| `master` | 遗留 | 忽略 |

**建议：** 以 `linjingjing` 分支为集成分支（或先把 linjingjing 合并进 main）。README 中承诺的 `VisualizationView.vue` 目前还不存在，本仓库（viewer）提供了参考实现，见第 3 节。

## 2. 注入契约（README 约定："threeDgsRenderer"）

- 注入 key：**`"threeDgsRenderer"`**（源码：`src/composables/useThreeDgsRenderer.js`）
- 祖先组件（VisualizationView）setup 中：
  ```js
  import { provideThreeDgsRenderer } from '.../composables/useThreeDgsRenderer.js'
  const setRenderer = provideThreeDgsRenderer()   // 建立注入通道
  // 拿到 ThreeDgsViewer 的渲染器实例后：
  setRenderer(viewerRef.value.getRenderer())
  ```
- 后代组件：
  ```js
  import { useThreeDgsRenderer } from '.../composables/useThreeDgsRenderer.js'
  const rendererRef = useThreeDgsRenderer()        // shallowRef，.value 为渲染器实例（加载前为 null）
  ```

## 3. ThreeDgsViewer 暴露的接口（defineExpose）

| 接口 | 签名 | 说明 |
|------|------|------|
| `getRenderer()` | `() => ThreeDgsRenderer` | 获取渲染器实例（用于注入） |
| `loadModelByPath(path, meta)` | `Promise<void>` | 按资源地址加载模型，走内部进度/失败 UI；`meta = { id, name, size, progressive }` |

**渲染器实例（ThreeDgsRenderer）常用方法：**

| 方法 | 说明 |
|------|------|
| `loadSplat(url, { progressive, onProgress })` | 加载 3DGS 模型（流式可选，完成才 resolve） |
| `unloadCurrentSplat()` | 卸载当前 3DGS（异步，切换前必须 await） |
| `loadGLTF(url, { flipY, position, scale })` | 叠加 glTF 网格模型 |
| `unloadGLTF(model?)` / `setGLTFTransform(model, {position, scale})` / `autoPlaceGLTF(model)` | glTF 卸载 / 调整 / 自动摆放 |
| `fitToModel()` / `resetView()` | 相机适配 / 复位 |
| `getModelInfo()` | `{ splatCount, center, size, radius }` |
| `getCapabilities()` | `{ backend, webgpuSupported, crossOriginIsolated }` |
| `pickAt(x, y)` / `onPick` 回调 / `clearPickMarker()` | 点击拾取 |
| `start()` / `stop()` / `dispose()` / `resize()` | 生命周期 |

## 4. 模型 API 字段约定（待与卓奕臻后端对齐）

模拟实现见 `src/reference/VisualizationView.vue` 的 `MOCK_MODELS`，约定字段：

```json
{ "id": "doll", "name": "玩偶（老师提供）", "path": "/models/export.ply", "size": "36.8 MB" }
```

后端 `/api/models/:id` 就绪后，把 `fetchModelInfo()` 里的 MOCK 替换为 `fetch` 即可（代码里已留 TODO）。

## 5. 集成路线 A：源码合并（真 provide/inject，README 契约）

把 viewer 的关键文件并入 `frontend/src/`（同一 Vue 应用）：

1. 拷贝文件：
   - `src/renderer/ThreeDgsRenderer.js`（核心，框架无关）
   - `src/components/ThreeDgsViewer.vue`（含样式）
   - `src/composables/useThreeDgsRenderer.js`（注入契约）
   - `src/reference/VisualizationView.vue` + `ModelStatsCard.vue`（参考页，可改造）
   - `src/config/models.js`（模型清单，可删改用 API 驱动）
   - `public/models/`、`public/libs/draco/`（模型与 Draco 解码器）
2. `frontend/package.json` 增加依赖：
   ```json
   "three": "^0.170.0",
   "@mkkellogg/gaussian-splats-3d": "0.4.7"
   ```
   （注意包名带 @mkkellogg 作用域，裸名 gaussian-splats-3d 是冒名旧包，勿用）
3. `frontend/vite.config.js` 必须加跨源隔离响应头（否则排序 worker 崩溃 → 黑屏）：
   ```js
   server: { headers: {
     'Cross-Origin-Opener-Policy': 'same-origin',
     'Cross-Origin-Embedder-Policy': 'require-corp',
   } }
   ```
   ⚠️ 生产环境（FastAPI 托管）时主站后端也要返回这两个响应头。
4. `frontend/src/router/index.js` 注册路由（如 `/visualization` → VisualizationView）。

## 6. 集成路线 B：独立构建 + iframe（保底方案）

若源码合并排期困难：`npm run build` 产物放主站 `static/viewer/`，平台页 `<iframe src="/static/viewer/index.html">`。
注意：跨构建边界 provide/inject 不生效，通信靠 URL 参数（如 `?model=point-cloud`）。
此路线改动最小、职责最清晰；provide/inject 契约仅源码合并时生效。

## 7. 其他注意事项

- **Draco 解码器**已本地托管在 `public/libs/draco/`（不依赖外部 CDN），glTF 加载默认挂载 DRACOLoader
- **坐标系**：3DGS 场景惯例 Y 轴向下（camera.up = (0,-1,0)）；常规 glTF（Y 向上）默认绕 Z 轴翻转 180°，可按模型配置 `flipY: false` 覆盖
- **性能**：已启用共享内存排序 worker（依赖第 5.3 节的响应头）；GPU 加速排序（gpuAcceleratedSort）经实测在 Chrome 下有读回饿死缺陷，已永久关闭（详见 ThreeDgsRenderer.js 注释）
- **模型大文件不进 git**（.gitignore 已约定），通过文件服务器共享
