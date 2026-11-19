/**
 * 可用 3DGS 模型清单
 *
 * 老师提供新模型时：把 .ply 文件放进 public/models/ 目录，
 * 然后在这里加一项即可出现在页面顶部的模型选择栏中。
 *
 * progressive：流式加载（边下载边显示，大文件建议 true）。
 * 集成进主网站后，path 可改为绝对地址（如 http://... 或 /static/viewer/models/xxx.ply）。
 */
// 路径用 BASE_URL 前缀：适配 base: './' 时构建产物可放任意子目录托管
const MODEL_BASE = import.meta.env.BASE_URL + 'models/'

export const MODELS = [
  { id: 'doll', name: '玩偶（老师提供）', path: MODEL_BASE + 'export.ply', size: '36.8 MB', progressive: true },
  { id: 'point-cloud', name: '点云场景（老师提供）', path: MODEL_BASE + 'point_cloud.ply', size: '141.9 MB', progressive: true },
]

/**
 * 可叠加的 glTF 网格模型清单（与 3DGS 泼溅模型同场景共存）
 *
 * 宋子祥组交付网格修复后的 glTF 时：把 .glb/.gltf 放进 public/models/gltf/，
 * 在这里加一项即可出现在页面顶部的 glTF 切换按钮中。
 *
 * flipY：常规 glTF 是 Y 轴向上，3DGS 场景惯例是 Y 轴向下，需要翻转（默认 true）。
 * 若上游交付的模型已按 3DGS 坐标系导出（Y 向下），把该项设为 false 即可。
 * position：位置 [x, y, z]（场景 Y 轴向下惯例，负 Y 是"上方"）。
 *   不写则自动摆放到泼溅模型包围盒旁边。
 * scale：等比缩放（1 = 模型原始尺寸）。
 * 页面里的 glTF 调整面板可以实时调这两项，调好后把数值写回这里作为默认值。
 */
export const GLTF_MODELS = [
  {
    id: 'ferrari',
    name: '法拉利跑车（glTF）',
    path: MODEL_BASE + 'gltf/ferrari.glb',
    flipY: true,
    // position: [0, 0, 0], // 调好满意后把数值写回这里固定
    scale: 1,
  },
]
