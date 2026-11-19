import { inject, provide, shallowRef } from 'vue'

/**
 * 3DGS 渲染器注入契约（第 9 步：对接林晶晶的平台前端 VisualizationView）
 *
 * 契约 key 与协作仓库 README 一致："threeDgsRenderer"。
 * 用法：
 *   - 持有渲染器的组件（如 VisualizationView）在 setup 里调用
 *     provideThreeDgsRenderer() 拿到 setter；拿到 ThreeDgsViewer 暴露的
 *     渲染器实例后 setter(renderer) 完成注入。
 *   - 任意后代组件调用 useThreeDgsRenderer() 获取注入的 shallowRef，
 *     通过 .value 访问渲染器实例（加载前为 null）。
 */
export const RENDERER_INJECTION_KEY = 'threeDgsRenderer'

/**
 * 在祖先组件 setup 中调用，建立注入通道。
 * @returns {(renderer: import('../renderer/ThreeDgsRenderer.js').ThreeDgsRenderer) => void}
 *   把渲染器实例写入注入槽的 setter（拿到实例后调用一次即可）
 */
export function provideThreeDgsRenderer() {
  const rendererRef = shallowRef(null)
  provide(RENDERER_INJECTION_KEY, rendererRef)
  return (renderer) => {
    rendererRef.value = renderer
  }
}

/**
 * 在后代组件中获取注入的渲染器引用。
 * @returns {import('vue').ShallowRef<import('../renderer/ThreeDgsRenderer.js').ThreeDgsRenderer|null> | null}
 *   未注入时返回 null（渲染器实例加载完成前 .value 为 null）
 */
export function useThreeDgsRenderer() {
  return inject(RENDERER_INJECTION_KEY, null)
}
