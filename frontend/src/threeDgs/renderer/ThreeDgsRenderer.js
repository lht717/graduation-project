import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js'
import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d'

/**
 * 框架无关的 3DGS 渲染器核心类（毕设核心模块）
 *
 * - 拥有自己的 THREE.Scene / Camera / WebGLRenderer / OrbitControls
 * - 通过 threeScene 选项把高斯泼溅渲染进同一 Three.js 场景，
 *   为后续 glTF 网格模型共存、点击拾取铺路
 * - selfDrivenMode = false，渲染循环由本类驱动，便于与 Vue 生命周期对接
 *
 * 用法：
 *   const renderer = new ThreeDgsRenderer(container)
 *   renderer.start()
 *   await renderer.loadSplat('/models/xxx.ply', { onProgress })
 */
export class ThreeDgsRenderer {
  constructor(container, options = {}) {
    if (!container) throw new Error('ThreeDgsRenderer: 容器元素不能为空')
    this.container = container

    const width = container.clientWidth || 1
    const height = container.clientHeight || 1

    // —— 场景 ——
    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0x111a22)

    // —— 光照：3DGS 泼溅材质无光照不受影响，为 glTF 网格模型（第 6 步）提供照明 ——
    this.scene.add(new THREE.AmbientLight(0xffffff, 1.4))
    this._directionalLight = new THREE.DirectionalLight(0xffffff, 2.5)
    this._directionalLight.position.set(4, -6, 8)
    this.scene.add(this._directionalLight, this._directionalLight.target) // target 默认在原点，需加入场景

    // —— 已加载的 glTF 模型根节点列表（第 6 步：与 3DGS 同场景共存）——
    this._gltfModels = []
    // —— 最近一次加载的下载进度（第 7 步 7b 流式加载完成信号用）——
    this._lastLoadProgress = 0

    // —— 渲染能力（第 8 步：WebGL2 兜底 + WebGPU 渐进增强的能力检测）——
    // 当前渲染后端固定为 WebGL2（three r170 本身要求 WebGL2；库 0.4.7 已核实
    // 源码无任何 WebGPU 路径）。WebGPU 只做能力检测展示，计算扩展点见
    // setDistanceComputer() 的接口契约注释。
    this.capabilities = {
      backend: 'webgl2',
      webgpuSupported: typeof navigator !== 'undefined' && !!navigator.gpu,
      crossOriginIsolated: typeof window !== 'undefined' && window.crossOriginIsolated === true,
    }

    // —— 相机（3DGS 惯例：Y 轴向下为 up）——
    this.camera = new THREE.PerspectiveCamera(60, width / height, 0.05, 500)
    this.camera.up.set(0, -1, 0)
    this.camera.position.set(0, -1.5, 4.5)
    this.camera.lookAt(0, 0, 0)

    // —— 渲染器（WebGL2 兜底基线，WebGPU 渐进增强在第 8 步加入）——
    this.renderer = new THREE.WebGLRenderer({ antialias: true })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setSize(width, height)
    container.appendChild(this.renderer.domElement)

    // —— 轨道控制：左键旋转 / 滚轮缩放 / 右键平移 ——
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.target.set(0, 0, 0)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    // 初始范围占位值，加载模型后由 fitToModel() 按实际尺寸重新设定
    this.controls.minDistance = 0.2
    this.controls.maxDistance = 500

    // —— 交互细节：光标反馈 + 双击复位视角 ——
    this._fittedView = null // 适配模型后的视角（双击复位用）
    this.renderer.domElement.style.cursor = 'grab'
    this._onControlsStart = () => { this.renderer.domElement.style.cursor = 'grabbing' }
    this._onControlsEnd = () => { this.renderer.domElement.style.cursor = 'grab' }
    this.controls.addEventListener('start', this._onControlsStart)
    this.controls.addEventListener('end', this._onControlsEnd)
    this._onDblClick = () => this.resetView()
    this.renderer.domElement.addEventListener('dblclick', this._onDblClick)

    // —— 点击拾取：按下/抬起位移和耗时都小才算"单击"，拖动交给 OrbitControls ——
    this.onPick = null // (hit: { position: Vector3, distance: number } | null) => void
    this._pointerDownPos = null
    this._pointerDownTime = 0
    this._onPointerDown = (e) => {
      if (e.button !== 0) return
      this._pointerDownPos = { x: e.clientX, y: e.clientY }
      this._pointerDownTime = performance.now()
    }
    this._onPointerUp = (e) => {
      if (e.button !== 0 || !this._pointerDownPos) return
      const dx = e.clientX - this._pointerDownPos.x
      const dy = e.clientY - this._pointerDownPos.y
      const dt = performance.now() - this._pointerDownTime
      this._pointerDownPos = null
      if (Math.hypot(dx, dy) > 5 || dt > 500) return // 视为拖动，不拾取
      const hit = this.pickAt(e.clientX, e.clientY)
      this._applyPick(hit)
    }
    this.renderer.domElement.addEventListener('pointerdown', this._onPointerDown)
    this.renderer.domElement.addEventListener('pointerup', this._onPointerUp)

    // —— 拾取标记（小球，首次拾取时创建）——
    this._pickMarker = null
    this._modelBox = null // 当前模型包围盒（fitToModel 时记录）
    this._modelRadius = 1

    // —— 3DGS 查看器（渲染进自有场景，渲染循环由本类驱动）——
    this.splatViewer = new GaussianSplats3D.Viewer({
      threeScene: this.scene,
      renderer: this.renderer,
      camera: this.camera,
      selfDrivenMode: false,
      useBuiltInControls: false,
      // —— 第 7 步性能优化结论（7a，2026-11-19 逐个开关实测）——
      // sharedMemoryForWorkers: true —— 排序 worker 与主线程共享内存，省掉每帧数组拷贝。
      //   依赖浏览器跨源隔离（COOP/COEP 响应头，见 vite.config.js），
      //   未隔离时排序 worker 里 new SharedArrayBuffer() 会抛错导致模型黑屏；
      //   集成主站时 FastAPI 也要加这两个响应头。
      // gpuAcceleratedSort: false —— 0.4.7 的 GPU 距离计算用 transform feedback 写完距离缓冲后
      //   fenceSync 等待整条 GPU 命令队列排空才读回（SplatMesh.js:1771），大场景下队列被
      //   泼溅渲染塞满，读回永远赶不上写入（Chrome 警告刷屏），排序结果交付不了 → 黑屏。
      //   实测判定为库的结构性缺陷，永久关闭；性能提升只采用共享内存方案。
      sharedMemoryForWorkers: true,
      gpuAcceleratedSort: false,
      logLevel: GaussianSplats3D.LogLevel.None,
      ...options.viewerOptions,
    })

    // —— 渲染循环与容器自适应 ——
    this._frameHandle = null
    this._running = false
    this._resizeObserver = new ResizeObserver(() => this.resize())
    this._resizeObserver.observe(container)
  }

  /**
   * 加载一个 3DGS 模型（.ply / .ksplat / .splat）
   * @param {string} url 模型地址（相对或绝对 URL）
   * @param {object} options
   * @param {(percent: number, percentLabel: string) => void} [options.onProgress] 加载进度回调（0-100）
   * @param {boolean} [options.progressive=false] 流式加载（第 7 步 7b）：边下载边构建边渲染，
   *   大模型不必等整个文件下载完就能看到内容。注意流式时 addSplatScene 在第一段构建完
   *   就 resolve（库源码 13110），此时包围盒不完整，必须等"全部下载+最终构建完成"信号
   *   （见 _waitForProgressiveLoadComplete）再 fitToModel。
   */
  async loadSplat(url, options = {}) {
    const { onProgress, progressive = false } = options
    this._lastLoadProgress = 0
    await this.splatViewer.addSplatScene(url, {
      splatAlphaRemovalThreshold: 5,
      progressiveLoad: progressive,
      showLoadingUI: false, // 由 Vue 层展示加载状态
      ...options.loadOptions,
      onProgress: (percent, percentLabel) => {
        this._lastLoadProgress = percent
        if (onProgress) onProgress(percent, percentLabel)
      },
    })
    if (progressive) {
      await this._waitForProgressiveLoadComplete()
    }
    // 相机适配模型包围盒：轨道中心对准模型中心，距离按模型尺寸设定
    this.fitToModel()
    return this
  }

  /**
   * 流式加载完成信号（progressiveLoad 模式专用）：
   * 1) 首选库的最终构建 promise（splatSceneDownloadAndBuildPromise，最后一段的构建
   *    完成时 resolve，库源码 13112）——精确信号，正常多段文件都会命中；
   * 2) 兜底：下载进度到 100% 且点数连续稳定 3 秒——应对超小单段文件（<256KB），
   *    库在单段文件时不会 resolve 上述 promise（源码 13109 的 if/else-if 只走
   *    firstBuild 分支），此时构建其实已全部完成，稳定性判断立即成立。
   */
  async _waitForProgressiveLoadComplete() {
    const finalPromise = this.splatViewer.splatSceneDownloadAndBuildPromise
    const stabilityPromise = (async () => {
      const mesh = this.splatViewer.getSplatMesh()
      let lastCount = -1
      let stableChecks = 0
      while (stableChecks < 12) { // 12 × 250ms = 3 秒稳定窗口
        await new Promise((resolve) => setTimeout(resolve, 250))
        const count = mesh ? mesh.getSplatCount() : 0
        if (this._lastLoadProgress >= 100 && count === lastCount) stableChecks++
        else stableChecks = 0
        lastCount = count
      }
    })()
    if (finalPromise) {
      await Promise.race([finalPromise, stabilityPromise])
    } else {
      await stabilityPromise
    }
  }

  /**
   * 卸载当前已加载的 3DGS 模型（切换模型前调用，释放显存/内存）。
   * 库的 removeSplatScene 是异步的，且卸载完成前不允许加载新模型，必须 await。
   */
  async unloadCurrentSplat() {
    if (this.splatViewer.getSceneCount() > 0) {
      await this.splatViewer.removeSplatScene(0, false)
    }
    this._fittedView = null
    this._modelBox = null
    this.clearPickMarker()
  }

  /**
   * 加载 glTF 网格模型，与 3DGS 泼溅同场景共存（需求：双格式渲染）。
   * 库在 threeScene 模式下每帧先渲染场景中的普通物体（含本类场景里的 glTF），
   * 再在其上叠加泼溅，因此 glTF 加入 this.scene 即可被自动渲染，无需额外渲染代码。
   * @param {string} url .gltf / .glb 地址
   * @param {object} [options]
   * @param {(percent: number) => void} [options.onProgress] 下载进度（0-100）
   * @param {boolean} [options.flipY=true] 常规 glTF 是 Y 轴向上，而 3DGS 场景惯例是
   *   Y 轴向下（相机 up = (0,-1,0)），需要绕 Z 轴旋转 180° 转正（纯旋转，非镜像）。
   *   若上游（网格修复组）交付的模型已按 3DGS 坐标系导出（Y 向下），则传 false。
   * @param {number[]} [options.position] 初始位置 [x, y, z]（Y 轴向下惯例）；
   *   不传时自动摆放到当前泼溅模型包围盒旁边（避免被泼溅遮挡看不见）
   * @param {number} [options.scale=1] 初始等比缩放
   * @returns {Promise<THREE.Object3D>} glTF 场景根节点
   */
  async loadGLTF(url, options = {}) {
    const { onProgress, flipY = true, position = null, scale = 1 } = options
    const gltfLoader = new GLTFLoader()
    // Draco 几何压缩解码器（本地托管在 public/libs/draco/，不依赖外部 CDN；
    // 上游网格修复组交付的 glTF 大概率也用了 Draco 压缩，故默认挂载）
    const dracoLoader = new DRACOLoader()
    dracoLoader.setDecoderPath(import.meta.env.BASE_URL + 'libs/draco/gltf/')
    gltfLoader.setDRACOLoader(dracoLoader)
    try {
      const gltf = await gltfLoader.loadAsync(url, (e) => {
        if (onProgress && e.total > 0) onProgress((e.loaded / e.total) * 100)
      })
      const model = gltf.scene
      if (flipY) model.rotation.z = Math.PI // Y 向上(glTF) → Y 向下(3DGS 场景惯例)
      model.scale.setScalar(scale)
      if (position) {
        model.position.set(position[0], position[1], position[2])
      } else {
        this.autoPlaceGLTF(model) // 未指定位置：摆到泼溅模型旁边
      }
      this._gltfModels.push(model)
      this.scene.add(model)
      this.fitToModel() // 相机按泼溅+glTF 合并包围盒重新适配
      return model
    } finally {
      dracoLoader.dispose() // 终止解码 worker 池，释放内存
    }
  }

  /**
   * 实时调整 glTF 模型的位置与大小（供 UI 调整面板调用）。
   * @param {THREE.Object3D} model 要调整的模型（loadGLTF 的返回值）
   * @param {object} transform
   * @param {number[]} [transform.position] 位置 [x, y, z]（Y 轴向下惯例）
   * @param {number} [transform.scale] 等比缩放
   */
  setGLTFTransform(model, { position, scale } = {}) {
    if (!model) return
    if (position) model.position.set(position[0], position[1], position[2])
    if (scale !== undefined) model.scale.setScalar(scale)
  }

  /**
   * 把 glTF 模型自动摆放到当前泼溅模型包围盒的旁边（沿 +X 方向错开，留 5cm 间隙）。
   * 避免 glTF 默认位置（原点）落在泼溅模型内部被遮挡看不见。
   * @param {THREE.Object3D} model glTF 模型根节点
   */
  autoPlaceGLTF(model) {
    if (!model) return
    const mesh = this.splatViewer.getSplatMesh()
    const splatBox = mesh ? new THREE.Box3().setFromObject(mesh) : null
    if (splatBox && !splatBox.isEmpty()) {
      const center = splatBox.getCenter(new THREE.Vector3())
      const splatRadius = splatBox.getBoundingSphere(new THREE.Sphere()).radius
      const gltfHalfX = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3()).x / 2
      model.position.set(center.x + splatRadius + gltfHalfX + 0.05, center.y, center.z)
    } else {
      model.position.set(0, 0, 0)
    }
  }

  /**
   * 卸载 glTF 模型：从场景移除并释放几何体/材质/贴图等 GPU 资源。
   * @param {THREE.Object3D} [model] 要卸载的模型；不传则卸载全部
   */
  unloadGLTF(model = null) {
    const targets = model ? [model] : [...this._gltfModels]
    for (const target of targets) {
      const idx = this._gltfModels.indexOf(target)
      if (idx >= 0) this._gltfModels.splice(idx, 1)
      this.scene.remove(target)
      target.traverse((node) => {
        if (node.geometry) node.geometry.dispose()
        const materials = Array.isArray(node.material) ? node.material : node.material ? [node.material] : []
        for (const mat of materials) {
          for (const value of Object.values(mat)) {
            if (value && value.isTexture) value.dispose()
          }
          mat.dispose()
        }
      })
    }
    if (targets.length > 0) this.fitToModel()
  }

  /**
   * 相机适配：适配范围 = 泼溅包围盒 ∪ 所有 glTF 模型包围盒（第 6 步双格式共存）。
   * 保持当前观察方向，把轨道中心移到适配范围中心，按范围尺寸重新设定
   * 相机距离、缩放范围与视锥裁剪面。
   * @returns {boolean} 是否成功适配（无任何模型或包围盒为空时返回 false）
   */
  fitToModel(margin = 1.25) {
    const mesh = this.splatViewer.getSplatMesh()
    const fitBox = new THREE.Box3()
    if (mesh) fitBox.union(new THREE.Box3().setFromObject(mesh))
    for (const gltfModel of this._gltfModels) fitBox.expandByObject(gltfModel)
    if (fitBox.isEmpty()) return false

    // _modelBox 只记纯泼溅包围盒（信息面板数据源），不混入 glTF
    this._modelBox = mesh ? new THREE.Box3().setFromObject(mesh) : null

    const center = fitBox.getCenter(new THREE.Vector3())
    const radius = fitBox.getBoundingSphere(new THREE.Sphere()).radius
    this._modelRadius = radius

    // 平行光跟随适配中心偏移，保证偏离原点的模型（如房间场景）上的 glTF 也有照明
    this._directionalLight.position.copy(center).add(new THREE.Vector3(4, -6, 8))

    // 保持当前观察方向，仅调整距离；方向退化时给一个默认视角
    const direction = this.camera.position.clone().sub(this.controls.target).normalize()
    if (direction.lengthSq() < 1e-6) direction.set(0, -0.35, 1).normalize()
    const fov = THREE.MathUtils.degToRad(this.camera.fov)
    const distance = (radius / Math.sin(fov / 2)) * margin

    this.controls.target.copy(center)
    this.camera.position.copy(center).addScaledVector(direction, distance)

    // 缩放范围与视锥裁剪面随模型尺寸调整
    this.controls.minDistance = Math.max(radius * 0.15, 0.001)
    this.controls.maxDistance = distance * 6
    this.camera.near = Math.max(distance / 1000, 0.001)
    this.camera.far = Math.max(distance * 10, 10)
    this.camera.updateProjectionMatrix()
    this.controls.update()

    this._fittedView = { target: center.clone(), position: this.camera.position.clone() }
    return true
  }

  /** 复位到适配模型后的视角（双击触发） */
  resetView() {
    if (!this._fittedView) {
      this.fitToModel()
      return
    }
    this.controls.target.copy(this._fittedView.target)
    this.camera.position.copy(this._fittedView.position)
    this.controls.update()
  }

  /**
   * 屏幕坐标拾取：从视口坐标（CSS 像素，相对窗口）发射射线与泼溅模型求交。
   * 库的 Raycaster 类未导出，但其 Viewer 实例持有 raycaster 属性，直接复用。
   * 屏幕坐标与 getRenderDimensions() 同为 CSS 像素，单位一致。
   * @returns {{ position: THREE.Vector3, distance: number } | null} 最近命中点或 null
   */
  pickAt(clientX, clientY) {
    const mesh = this.splatViewer.getSplatMesh()
    if (!mesh) return null
    const rect = this.renderer.domElement.getBoundingClientRect()
    const screenPos = new THREE.Vector2(clientX - rect.left, clientY - rect.top)
    const dims = new THREE.Vector2()
    this.splatViewer.getRenderDimensions(dims)
    this.splatViewer.raycaster.setFromCameraAndScreenPosition(this.camera, screenPos, dims)
    const hits = []
    this.splatViewer.raycaster.intersectSplatMesh(mesh, hits)
    if (hits.length === 0) return null
    return { position: hits[0].origin.clone(), distance: hits[0].distance }
  }

  /** 命中：在命中点放置标记小球并回调；落空：隐藏标记并回调 null */
  _applyPick(hit) {
    if (hit) {
      this._ensurePickMarker()
      this._pickMarker.position.copy(hit.position)
      // 标记大小随模型尺寸缩放，避免大模型上小到看不见
      const r = Math.max(this._modelRadius * 0.02, 0.004)
      this._pickMarker.scale.setScalar(r)
      this._pickMarker.visible = true
    } else if (this._pickMarker) {
      this._pickMarker.visible = false
    }
    if (this.onPick) this.onPick(hit)
  }

  _ensurePickMarker() {
    if (this._pickMarker) return
    this._pickMarker = new THREE.Mesh(
      new THREE.SphereGeometry(1, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0xff6b6b }),
    )
    this._pickMarker.visible = false
    this.scene.add(this._pickMarker)
  }

  /** 隐藏拾取标记（切换模型、清空拾取时调用） */
  clearPickMarker() {
    if (this._pickMarker) this._pickMarker.visible = false
  }

  /**
   * 渲染能力信息（信息面板数据源，第 8 步能力检测）。
   * @returns {{ backend: string, webgpuSupported: boolean, crossOriginIsolated: boolean }}
   */
  getCapabilities() {
    return this.capabilities
  }

  /**
   * 【第 8 步架构预留】挂接"泼溅排序距离计算器"的扩展点（当前未启用，返回 false）。
   *
   * 背景：库 0.4.7 的排序流水线支持"预计算距离"路径——排序消息携带
   * usePrecomputedDistances: true 时，排序 worker 跳过 CPU 距离计算，直接读共享
   * 内存里的 sortWorkerPrecomputedDistances（库源码 14137 / 13485）。
   * 7a 曾用库自带的 WebGL transform feedback 实现该路径，因 fenceSync 等待整条
   * GPU 命令队列排空、读回永远赶不上写入而黑屏（详见构造函数 gpuAcceleratedSort 注释）。
   *
   * 未来 WebGPU 实现可在此挂接：用 WebGPU 计算着色器算好距离写入
   * SharedArrayBuffer 区域，再让 worker 走预计算路径。WebGPU 的异步 buffer
   * 映射（mapAsync）不存在 WebGL 的队列饿死问题，是这条路线的正解。
   *
   * @param {object} computer 需实现 computeDistances(mvpMatrix, outFloat32Array): Promise<void>
   * @returns {boolean} 是否成功挂接（当前未实现，恒为 false）
   */
  setDistanceComputer(computer) {
    return false // TODO(WebGPU): 按上述契约实现挂接逻辑
  }

  /**
   * 当前模型信息（信息面板数据源）。
   * @returns {{ splatCount: number, center: THREE.Vector3, size: THREE.Vector3, radius: number } | null}
   */
  getModelInfo() {
    const mesh = this.splatViewer.getSplatMesh()
    if (!mesh || !this._modelBox) return null
    return {
      splatCount: mesh.getSplatCount(),
      center: this._modelBox.getCenter(new THREE.Vector3()),
      size: this._modelBox.getSize(new THREE.Vector3()),
      radius: this._modelRadius,
    }
  }

  /** 启动渲染循环 */
  start() {
    if (this._running) return
    this._running = true
    const loop = () => {
      if (!this._running) return
      this._frameHandle = requestAnimationFrame(loop)
      this.controls.update()
      this.splatViewer.update()
      this.splatViewer.render()
    }
    loop()
  }

  /** 停止渲染循环（不释放资源） */
  stop() {
    this._running = false
    if (this._frameHandle) cancelAnimationFrame(this._frameHandle)
    this._frameHandle = null
  }

  /** 容器尺寸变化时自适应 */
  resize() {
    const width = this.container.clientWidth || 1
    const height = this.container.clientHeight || 1
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(width, height)
  }

  /** 释放全部资源（组件卸载时调用） */
  dispose() {
    this.stop()
    this._resizeObserver.disconnect()
    this.controls.removeEventListener('start', this._onControlsStart)
    this.controls.removeEventListener('end', this._onControlsEnd)
    this.renderer.domElement.removeEventListener('dblclick', this._onDblClick)
    this.renderer.domElement.removeEventListener('pointerdown', this._onPointerDown)
    this.renderer.domElement.removeEventListener('pointerup', this._onPointerUp)
    if (this._pickMarker) {
      this._pickMarker.geometry.dispose()
      this._pickMarker.material.dispose()
      this._pickMarker = null
    }
    this.unloadGLTF()
    this.splatViewer.dispose()
    this.controls.dispose()
    this.renderer.dispose()
    if (this.renderer.domElement.parentElement === this.container) {
      this.container.removeChild(this.renderer.domElement)
    }
  }
}
