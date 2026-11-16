<script setup>
import { computed, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useExperimentStore } from "@/stores/experiment.js";
import { resolveWsUrl } from "@/ws/url.js";

defineOptions({ name: "WorkspaceView" });

const exp = useExperimentStore();
const router = useRouter();
const route = useRoute();
const DEFAULT_EXPERIMENT_TYPE = "智能汽车视觉感知实验";
// 从实验中心卡片传入的类型，保存实验记录与顶栏标题都用它
const experimentType = computed(() => {
  const raw = Array.isArray(route.query.type) ? route.query.type[0] : route.query.type;
  const value = String(raw || "").trim();
  return value ? value.slice(0, 64) : DEFAULT_EXPERIMENT_TYPE;
});

const frontCanvas = ref(null);
const rearCanvas = ref(null);
const consoleBody = ref(null);
const modelFileInput = ref(null);
const modelSaveName = ref("");
const selectedFileName = ref("");
const uploadDisabled = ref(true);
const loadModelsDisabled = ref(false);

const frontHasFrame = ref(false);
const rearHasFrame = ref(false);

const recordName = ref("");

// 顶部居中的场景 tab：三个模式共用同一套页面布局，只有数据来源与启用范围不同
const SCENE_TABS = [
  { value: "simulation", label: "虚拟仿真", id: "simModeBtn" },
  { value: "hybrid", label: "虚实结合", id: "hybridModeBtn" },
  { value: "real", label: "真实场景", id: "realModeBtn" }
];

function selectScene(next) {
  exp.setMode(next);
}

let edgeSocket = null;
let edgeReconnectTimer = null;
let edgeFpsTimer = null;
const edgeWsConnected = ref(false);
const edgeWsConnecting = ref(false);
const edgeDevices = ref([]);
// 近期连接过的主板：设备一上线就记录到 localStorage，之后即使离线也保留条目，
// 不再使用写死的假设备目录；列表 = 历史记录 + 实时在线状态合并
const EDGE_RECENT_KEY = "edge_recent_devices";
const recentEdgeDevices = ref(loadRecentEdgeDevices());

function loadRecentEdgeDevices() {
  try {
    const raw = JSON.parse(localStorage.getItem(EDGE_RECENT_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((item) => item && item.id) : [];
  } catch {
    return [];
  }
}

function rememberEdgeDevices(list) {
  if (!Array.isArray(list) || !list.length) return;
  const now = Date.now();
  const map = new Map(recentEdgeDevices.value.map((device) => [device.id, device]));
  for (const dev of list) {
    const id = dev.device_id || dev.id;
    if (!id) continue;
    const prev = map.get(id) || {};
    map.set(id, {
      ...prev,
      id,
      name: dev.name || prev.name || id,
      vendor: dev.vendor || prev.vendor || "",
      memory: dev.model || prev.memory || "",
      deviceNo: dev.device_no || prev.deviceNo || "",
      lastSeen: now
    });
  }
  // 最多保留 8 条，按最近连接时间倒序
  recentEdgeDevices.value = [...map.values()]
    .sort((a, b) => (b.lastSeen || 0) - (a.lastSeen || 0))
    .slice(0, 8);
  try {
    localStorage.setItem(EDGE_RECENT_KEY, JSON.stringify(recentEdgeDevices.value));
  } catch {
    /* localStorage 不可用时只保留在内存里 */
  }
}

const selectedEdgeDeviceId = ref("");
const edgeDetectionData = ref(null);
// 边缘主板随检测结果回传的缩略图（data:image/jpeg;base64,...），用作画布底图
const edgeThumb = ref("");
const edgeCommandStatus = ref("");
// 以下为对接 edge_ws_server 后新增的展示字段（模型名 / 帧尺寸 / 推理耗时 / 上报帧率）
const edgeModelName = ref("");
const edgeFrameSize = ref({ width: 0, height: 0 });
const edgeInferMs = ref(0);
const edgeSeq = ref(0);
const edgeFps = ref(0);
const edgeFramesThisSecond = ref(0);
const selectedEdgeDevice = computed(
  () => edgeDeviceList.value.find((device) => device.id === selectedEdgeDeviceId.value) || edgeDeviceList.value[0] || null
);
const edgeDeviceList = computed(() => {
  // 基础列表来自"近期连过的主板"（localStorage），默认离线
  const devices = new Map(
    recentEdgeDevices.value.map((device) => [
      device.id,
      {
        ...device,
        meta: [device.vendor, device.memory, device.deviceNo].filter(Boolean).join(" · "),
        status: "offline",
        frames: 0,
        online: 0
      }
    ])
  );
  for (const online of edgeDevices.value) {
    // 服务端字段：device_id / name / vendor / model / device_no / status / detection_count / online_seconds
    const id = online.device_id || online.id;
    const current = devices.get(id) || { id, name: online.name || id, vendor: "", memory: "", deviceNo: "", meta: "" };
    devices.set(id, {
      ...current,
      name: online.name || current.name,
      vendor: online.vendor || current.vendor,
      memory: online.model || current.memory,
      deviceNo: online.device_no || current.deviceNo,
      meta: [online.vendor || current.vendor, online.model || current.memory, online.device_no || current.deviceNo]
        .filter(Boolean)
        .join(" · "),
      status: online.status || "idle",
      frames: Number(online.detection_count) || 0,
      online: Number(online.online_seconds) || 0,
      remote: online.remote_addr || ""
    });
  }
  return [...devices.values()];
});
const edgeDeviceConnected = computed(
  () => Boolean(selectedEdgeDevice.value && selectedEdgeDevice.value.status !== "offline")
);

const edgeDetections = computed(() => {
  const data = edgeDetectionData.value;
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== "object") return [];
  const detections = data.detections ?? data.objects ?? data.results;
  return Array.isArray(detections) ? detections : [];
});
function edgeField(detection, keys, fallback = "--") {
  for (const key of keys) {
    const value = detection?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return fallback;
}

function edgeConfidence(detection) {
  const value = Number(edgeField(detection, ["confidence", "score"], NaN));
  if (!Number.isFinite(value)) return "--";
  return `${(value <= 1 ? value * 100 : value).toFixed(1)}%`;
}

/* ---------------- 边缘主板检测画布 ----------------
 * 数据全部来自主板：thumb 是主板用 cv2.imencode 压好的 JPEG 缩略图（data URI），
 * detections[].bbox 是原始帧坐标系下的绝对像素 xyxy。
 * 画布内部尺寸直接设成 frame 尺寸，bbox 就能 1:1 画上去，不存在缩放误差；
 * 显示大小交给 CSS（width:100%），所以不同分辨率的摄像头都不用改代码。
 */
const EDGE_BOX_COLORS = ["#22c55e", "#f59e0b", "#38bdf8", "#f472b6", "#a78bfa", "#facc15"];
let edgeFrameToken = 0;   // 帧序号：缩略图解码是异步的，用它丢弃"迟到的旧帧"

function edgeRawBox(detection) {
  // 服务端归一化后是 bbox；兼容设备端原始字段 box / xyxy / 嵌套在 raw 里的情况
  const box = detection?.bbox ?? detection?.box ?? detection?.xyxy ?? detection?.raw?.bbox ?? detection?.raw?.box;
  return Array.isArray(box) && box.length >= 4 ? box : null;
}

function drawEdgeBoxes(ctx, width, height) {
  const fontSize = Math.max(12, Math.round(height / 34));
  const lineWidth = Math.max(2, Math.round(width / 320));
  ctx.font = `500 ${fontSize}px system-ui, -apple-system, sans-serif`;
  ctx.textBaseline = "alphabetic";

  edgeDetections.value.forEach((detection, index) => {
    const box = edgeRawBox(detection);
    if (!box) return;
    let [x1, y1, x2, y2] = box.slice(0, 4).map(Number);
    if (![x1, y1, x2, y2].every(Number.isFinite)) return;
    // 少数设备给的是 0~1 归一化坐标，这里自动识别并换算成像素
    if (x1 <= 1 && y1 <= 1 && x2 <= 1 && y2 <= 1) {
      x1 *= width; x2 *= width; y1 *= height; y2 *= height;
    }
    // 统一成左上/右下的顺序，避免设备端给成 (x2,y2,x1,y1) 时画出空框
    const left = Math.min(x1, x2), top = Math.min(y1, y2);
    const boxWidth = Math.max(1, Math.abs(x2 - x1)), boxHeight = Math.max(1, Math.abs(y2 - y1));
    const color = EDGE_BOX_COLORS[index % EDGE_BOX_COLORS.length];

    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.strokeRect(left, top, boxWidth, boxHeight);

    const label = `${edgeField(detection, ["class_name", "class", "label", "category", "name"])} ${edgeConfidence(detection)}`;
    const labelWidth = ctx.measureText(label).width + 10;
    const labelHeight = fontSize + 8;
    // 框贴住画面顶部时，标签塞到框内，否则会画到画布外面
    const labelTop = top - labelHeight < 0 ? top : top - labelHeight;

    ctx.fillStyle = color;
    ctx.fillRect(left - lineWidth / 2, labelTop, labelWidth, labelHeight);
    ctx.fillStyle = "#0b0f14";
    ctx.fillText(label, left + 5, labelTop + labelHeight - 6);
  });
}

// 边缘画面直接画进左侧「AI 感知识别」画布：虚实结合模式下它只有这一个数据源，
// 不再单独占一块面板，老师看到的"AI 识别画面"就是主板上传的画面 + 主板算出的框。
function renderEdgeCanvas() {
  const canvas = frontCanvas.value;
  if (!canvas) return;
  const width = Number(edgeFrameSize.value.width) || 0;
  const height = Number(edgeFrameSize.value.height) || 0;
  if (!width || !height) return;

  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const token = ++edgeFrameToken;
  const thumb = edgeThumb.value;

  if (thumb) {
    const image = new Image();
    image.onload = () => {
      if (token !== edgeFrameToken) return;   // 已经有更新的帧了，丢弃这张旧图
      // 底图铺满整块画布，同时把上一帧的框覆盖掉，不需要 clearRect（避免闪黑）
      ctx.drawImage(image, 0, 0, width, height);
      drawEdgeBoxes(ctx, width, height);
      frontHasFrame.value = true;
      exp.countFrame();
    };
    image.onerror = () => {
      if (token !== edgeFrameToken) return;
      ctx.clearRect(0, 0, width, height);
      drawEdgeBoxes(ctx, width, height);
      frontHasFrame.value = true;
    };
    image.src = thumb;
    return;
  }

  // 设备端用 --thumb-width 0 关了缩略图：画布留深色底，框的位置和运动依旧可见
  ctx.fillStyle = "#0f172a";
  ctx.fillRect(0, 0, width, height);
  drawEdgeBoxes(ctx, width, height);
  frontHasFrame.value = true;
  exp.countFrame();
}

function clearEdgeCanvas() {
  const canvas = frontCanvas.value;
  if (!canvas) return;
  canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  frontHasFrame.value = false;
  // 切回虚拟仿真时恢复 CARLA 的 800×600：边缘帧可能是 640×480 甚至 1280×720，
  // 沿用下去会让 CARLA 画面按错误的内部分辨率绘制
  if (exp.isSimulation) {
    canvas.width = 800;
    canvas.height = 600;
  }
}

function edgeStatusText(status) {
  if (status === "idle") return "在线·空闲";
  if (status === "busy") return "在线·使用中";
  return "离线";
}

function applyEdgeDevices(list) {
  edgeDevices.value = Array.isArray(list) ? list : [];
  // 记录"近期连过的主板"（含刚上线的），供离线后继续展示
  rememberEdgeDevices(edgeDevices.value);
  // 选中的设备离线时，自动切到第一台在线设备，避免指令发给不存在的连接
  const stillOnline = edgeDevices.value.some((device) => (device.device_id || device.id) === selectedEdgeDeviceId.value);
  if (!stillOnline && edgeDevices.value.length) {
    selectedEdgeDeviceId.value = edgeDevices.value[0].device_id || edgeDevices.value[0].id;
  }
}

function handleEdgeDetection(message) {
  const deviceId = message.device_id;
  if (deviceId && deviceId !== selectedEdgeDeviceId.value) return;  // 只看当前选中设备的数据

  edgeDetectionData.value = message;
  edgeModelName.value = message.model || edgeModelName.value;
  edgeInferMs.value = Number(message.infer_ms) || 0;
  edgeSeq.value = Number(message.seq) || 0;
  if (message.frame?.width && message.frame?.height) {
    edgeFrameSize.value = { width: message.frame.width, height: message.frame.height };
  }
  // 每帧独立：这一帧没带图就把上一帧清掉，避免底图停住而框在动（看起来像"框飘了"）
  edgeThumb.value = typeof message.thumb === "string" ? message.thumb : "";
  edgeFramesThisSecond.value += 1;
  // 等 DOM 更新（首次渲染时 canvas 可能刚被 v-if 插进来）后再画
  nextTick(renderEdgeCanvas);
}

function handleEdgeMessage(event) {
  if (typeof event.data !== "string") {
    exp.log("边缘主板 WebSocket 收到非文本消息，已忽略", "err");
    return;
  }

  let message;
  try {
    message = JSON.parse(event.data);
  } catch (error) {
    exp.log(`边缘主板消息解析失败：${error.message}`, "err");
    return;
  }

  // 服务端在握手完成后会立刻推一份全量设备快照
  if (message.type === "device_list") {
    applyEdgeDevices(message.devices);
    exp.log(`边缘设备快照：在线 ${edgeDevices.value.length} 台`, edgeDevices.value.length ? "ok" : "warn");
    return;
  }

  if (message.type === "device_online" || message.type === "device_offline") {
    const online = message.type === "device_online";
    applyEdgeDevices(message.devices || edgeDevices.value);
    exp.log(
      `边缘设备${online ? "上线" : "离线"}：${message.device_id}${online ? "" : `（${message.reason || "断开"}）`}`,
      online ? "ok" : "warn"
    );
    return;
  }

  if (message.type === "detection") {
    handleEdgeDetection(message);
    return;
  }

  // 设备执行完指令后的回执（服务端把设备的 command_ack 原样广播出来）
  if (message.type === "command_ack") {
    const payload = message.payload || {};
    const ok = payload.ok !== false;
    edgeCommandStatus.value = `${payload.command || "指令"}：${payload.message || (ok ? "已执行" : "执行失败")}`;
    exp.log(`边缘回执 ${edgeCommandStatus.value}`, ok ? "ok" : "err");
    return;
  }

  if (message.type === "command_status") {
    if (message.ok === false) {
      edgeCommandStatus.value = `指令失败：${message.message || "后端拒绝"}`;
      exp.log(edgeCommandStatus.value, "err");
    }
    return;
  }

  if (message.type === "error") {
    edgeCommandStatus.value = `指令失败：${message.message || "后端错误"}`;
    exp.log(`边缘主板服务错误：${message.message || "未知错误"}`, "err");
  }
}

function connectEdge() {
  if (edgeSocket && (edgeSocket.readyState === WebSocket.CONNECTING || edgeSocket.readyState === WebSocket.OPEN)) return;
  window.clearTimeout(edgeReconnectTimer);
  edgeReconnectTimer = null;

  const token = localStorage.getItem("fusionlab_token");
  if (!token) {
    edgeCommandStatus.value = "请先登录后连接边缘主板";
    return;
  }
  // 与 main.py 合并后：设备端 /ws/edge，控制端 /ws/edge/panel（复用平台登录会话鉴权）
  const url = new URL(resolveWsUrl());
  url.pathname = "/ws/edge/panel";
  url.search = "";
  url.searchParams.set("token", token);
  url.searchParams.set("client", "workspace");
  edgeWsConnecting.value = true;
  edgeCommandStatus.value = "";
  exp.log("正在连接边缘设备服务…");

  try {
    edgeSocket = new WebSocket(url.href);
  } catch (error) {
    edgeWsConnecting.value = false;
    edgeWsConnected.value = false;
    exp.log(`边缘设备 WebSocket 创建失败：${error.message}`, "err");
    return;
  }

  const activeSocket = edgeSocket;
  activeSocket.onopen = () => {
    if (edgeSocket !== activeSocket) return;
    edgeWsConnecting.value = false;
    edgeWsConnected.value = true;
    exp.log("边缘设备服务已连接，等待主板上报", "ok");
    startEdgeFpsCounter();
  };
  activeSocket.onmessage = handleEdgeMessage;
  activeSocket.onerror = () => {
    if (edgeSocket !== activeSocket) return;
    edgeWsConnecting.value = false;
    exp.log("边缘设备服务连接错误：请确认 FastAPI 后端已启动", "err");
    activeSocket.close();
  };
  activeSocket.onclose = (event) => {
    if (edgeSocket !== activeSocket) return;
    edgeSocket = null;
    edgeWsConnecting.value = false;
    edgeWsConnected.value = false;
    edgeDevices.value = [];
    edgeDetectionData.value = null;
    edgeFps.value = 0;
    edgeFramesThisSecond.value = 0;
    window.clearInterval(edgeFpsTimer);
    edgeFpsTimer = null;
    const reason = event.code === 1008 ? "登录会话无效，请重新登录" : `code=${event.code}`;
    exp.log(`边缘设备服务已断开（${reason}）`, "warn");
  };
}

// 每秒统计一次上报帧率：只做展示，不影响收包
function startEdgeFpsCounter() {
  window.clearInterval(edgeFpsTimer);
  edgeFpsTimer = window.setInterval(() => {
    edgeFps.value = edgeFramesThisSecond.value;
    edgeFramesThisSecond.value = 0;
  }, 1000);
}

function disconnectEdge() {
  window.clearInterval(edgeFpsTimer);
  edgeFpsTimer = null;
  if (edgeSocket) {
    const activeSocket = edgeSocket;
    edgeSocket = null;
    activeSocket.onopen = null;
    activeSocket.onmessage = null;
    activeSocket.onerror = null;
    activeSocket.onclose = null;
    activeSocket.close();
  }
  edgeWsConnecting.value = false;
  edgeWsConnected.value = false;
  edgeDevices.value = [];
  edgeDetectionData.value = null;
  edgeThumb.value = "";
  nextTick(clearEdgeCanvas);
  edgeFps.value = 0;
  edgeFramesThisSecond.value = 0;
}

function reconnectEdge() {
  if (edgeWsConnecting.value) return;
  disconnectEdge();
  window.clearTimeout(edgeReconnectTimer);
  edgeReconnectTimer = window.setTimeout(() => {
    edgeReconnectTimer = null;
    connectEdge();
  }, 120);
}

function selectEdgeDevice(deviceId) {
  if (selectedEdgeDeviceId.value === deviceId) return;
  selectedEdgeDeviceId.value = deviceId;
  edgeDetectionData.value = null;
  edgeThumb.value = "";
  nextTick(clearEdgeCanvas);
  edgeCommandStatus.value = "";
}

function sendEdgeCommand(command, params = {}) {
  if (edgeSocket?.readyState !== WebSocket.OPEN) {
    edgeCommandStatus.value = "边缘设备服务未连接";
    exp.log("操作失败：边缘设备服务未连接", "err");
    return;
  }
  if (!edgeDeviceConnected.value) {
    edgeCommandStatus.value = "所选边缘主板当前离线";
    exp.log("操作失败：所选边缘主板当前离线", "err");
    return;
  }
  const labels = { start: "开启识别", stop: "关闭识别", switch_model: "切换主板模型" };
  const model = params.model ? `（${params.model}）` : "";
  try {
    edgeSocket.send(JSON.stringify({
      type: "command",
      command,
      device_id: selectedEdgeDeviceId.value,
      params
    }));
    edgeCommandStatus.value = `已向 ${selectedEdgeDeviceId.value} 下发${labels[command] || command}${model}…`;
  } catch (error) {
    edgeCommandStatus.value = `指令发送失败：${error.message}`;
    exp.log(`边缘主板指令发送失败：${error.message}`, "err");
  }
}

watch(
  () => exp.usesEdge,
  (edgeOn) => {
    if (edgeOn) {
      connectEdge();
      // 切到主板供图的场景时画布是刚挂载的，补一次绘制，避免等到下一帧才有内容
      nextTick(renderEdgeCanvas);
    } else {
      window.clearTimeout(edgeReconnectTimer);
      edgeReconnectTimer = null;
      disconnectEdge();
      nextTick(clearEdgeCanvas);
    }
  }
);

// 真实场景不接入 CARLA：进入时断开仿真连接并清空两路仿真画面，离开时再重新连回去
watch(
  () => exp.isRealScene,
  (real) => {
    if (real) {
      exp.disconnect();
      clearFrames();
      nextTick(clearEdgeCanvas);
    } else {
      exp.activate();
    }
  }
);

async function onSaveRecord() {
  await exp.saveExperimentRecord(recordName.value, experimentType.value);
}

const pendingObjectUrls = new Set();

/* ---------------- 帧绘制（对应原版 drawImageFrame） ---------------- */
function drawFrame(prefix, bytes) {
  const canvas = prefix === 0 ? frontCanvas.value : rearCanvas.value;
  if (!canvas) return;
  // 虚实结合模式下，左侧「AI 感知识别」画布改由边缘主板供图。
  // 一旦主板开始上报，就丢弃 CARLA 的前视帧，否则两个数据源会来回抢这块画布、画面闪烁。
  // 真实场景模式完全不接 CARLA，前视帧一律丢弃。
  if (prefix === 0 && exp.isRealScene) return;
  if (prefix === 0 && !exp.isSimulation && edgeDetectionData.value !== null) return;
  const context = canvas.getContext("2d");
  const objectUrl = URL.createObjectURL(new Blob([bytes], { type: "image/jpeg" }));
  pendingObjectUrls.add(objectUrl);
  const image = new Image();
  image.onload = () => {
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(objectUrl);
    pendingObjectUrls.delete(objectUrl);
    if (prefix === 0) {
      frontHasFrame.value = true;
      exp.countFrame();
    } else {
      rearHasFrame.value = true;
    }
  };
  image.onerror = () => {
    URL.revokeObjectURL(objectUrl);
    pendingObjectUrls.delete(objectUrl);
    exp.log(`无法解码 ${prefix === 0 ? "AI 感知" : "CARLA"} 图像帧`, "err");
  };
  image.src = objectUrl;
}

function clearFrames() {
  frontHasFrame.value = false;
  rearHasFrame.value = false;
  frontCanvas.value?.getContext("2d").clearRect(0, 0, 800, 600);
  rearCanvas.value?.getContext("2d").clearRect(0, 0, 800, 600);
}

/* ---------------- 模型上传交互 ---------------- */
function onFileChange() {
  const input = modelFileInput.value;
  const file = input?.files?.[0];
  uploadDisabled.value = !file;
  selectedFileName.value = file ? file.name : "";
  if (file) {
    modelSaveName.value = file.name;
    exp.setModelStatus(`已选择 ${file.name} · ${exp.formatBytes(file.size)}`);
  }
}

async function onUpload() {
  const file = modelFileInput.value?.files?.[0];
  const name = modelSaveName.value.trim();
  uploadDisabled.value = true;
  const ok = await exp.uploadModel(file, name);
  if (ok) {
    if (modelFileInput.value) modelFileInput.value.value = "";
    modelSaveName.value = "";
    selectedFileName.value = "";
  }
  uploadDisabled.value = !modelFileInput.value?.files?.[0];
}

async function onLoadModels() {
  loadModelsDisabled.value = true;
  try {
    await exp.loadSelectedModels();
  } finally {
    loadModelsDisabled.value = false;
  }
}

/* ---------------- 日志滚动 ---------------- */
watch(
  () => exp.logs.length,
  async () => {
    await nextTick();
    if (consoleBody.value) consoleBody.value.scrollTop = consoleBody.value.scrollHeight;
  }
);

/* ---------------- 车辆销毁时清空画面 ---------------- */
watch(
  () => exp.frameResetTick,
  () => clearFrames()
);

/* ---------------- 生命周期 ---------------- */
onMounted(() => {
  exp.setFrameHandler(drawFrame);
});

// 原版每次进入工作台都会 activate()：拉模型库 + 建立（或复用）WebSocket
// 真实场景只用边缘主板，不连 CARLA，只把模型库刷一遍
onActivated(() => {
  if (exp.isRealScene) {
    void exp.refreshModels();
  } else {
    exp.activate();
  }
  if (exp.usesEdge) connectEdge();
});

onDeactivated(() => {
  window.clearTimeout(edgeReconnectTimer);
  edgeReconnectTimer = null;
  disconnectEdge();
});

onUnmounted(() => {
  window.clearTimeout(edgeReconnectTimer);
  edgeReconnectTimer = null;
  exp.setFrameHandler(null);
  disconnectEdge();
  exp.disconnect();
  for (const objectUrl of pendingObjectUrls) URL.revokeObjectURL(objectUrl);
  pendingObjectUrls.clear();
});
</script>

<template>
  <section id="experimentView" class="workspace">
    <header class="work-contextbar">
      <div class="work-context-title">
        <button class="back-btn" id="backDashboard" aria-label="返回我的实验" @click="router.push('/dashboard')">←</button>
        <div class="work-title"><b>{{ experimentType }}</b><span id="workModeLabel">{{ exp.workModeLabel }}</span></div>
      </div>
      <nav class="scene-tabs" role="tablist" aria-label="实验场景切换">
        <button
          v-for="tab in SCENE_TABS"
          :id="tab.id"
          :key="tab.value"
          type="button"
          role="tab"
          :aria-selected="exp.mode === tab.value"
          :class="{ active: exp.mode === tab.value }"
          @click="selectScene(tab.value)"
        >{{ tab.label }}</button>
      </nav>
      <div class="work-context-meta">{{ exp.modeNote }}</div>
    </header>
    <div class="work-body">
      <aside class="sidebar">
        <div class="side-head">实验配置</div>
        <div class="block"><label>01 · AI 模型库</label><div class="model-box">
          <input id="modelFileInput" ref="modelFileInput" class="model-file" type="file" accept=".onnx" @change="onFileChange" />
          <input id="modelSaveName" v-model="modelSaveName" class="model-name" type="text" placeholder="上传后保存的文件名，例如 model_v2.onnx" />
          <div class="model-actions"><button id="uploadModelBtn" class="btn btn-soft" :disabled="uploadDisabled" @click="onUpload">上传模型</button><button id="refreshModelsBtn" class="btn btn-outline" @click="exp.refreshModels()">刷新列表</button></div>
          <div id="modelStatus" :class="exp.modelStatusState ? `model-status ${exp.modelStatusState}` : 'model-status'">{{ exp.modelStatus }}</div>
          <div id="modelLibrary" class="model-library">
            <template v-if="exp.models.length">
              <div v-for="model in exp.models" :key="model.name" class="model-item"><b>{{ model.name }}</b><span>{{ (model.active_roles || []).map((role) => role.toUpperCase()).join(' / ') ? `${(model.active_roles || []).map((role) => role.toUpperCase()).join(' / ')} · ` : '' }}{{ exp.formatBytes(Number(model.size) || 0) }}</span></div>
            </template>
            <div v-else-if="exp.modelsLoaded" class="model-item">暂无可用 ONNX 模型</div>
            <div v-else class="model-item"><b>正在读取模型库...</b><span>--</span></div>
          </div>
          <div class="model-slot"><label>车道线检测模型（UFLD兼容）</label><select id="ufldModelSelect" v-model="exp.ufldSelection" class="select"><option value="">未选择</option><option v-for="model in exp.models" :key="model.name" :value="model.name">{{ model.name }}</option></select></div>
          <div class="model-slot"><label>目标检测模型（YOLO兼容）</label><select id="yoloModelSelect" v-model="exp.yoloSelection" class="select"><option value="">未选择</option><option v-for="model in exp.models" :key="model.name" :value="model.name">{{ model.name }}</option></select></div>
          <button id="loadModelsBtn" class="btn btn-primary" style="width:100%;margin-top:8px" :disabled="loadModelsDisabled" @click="onLoadModels">加载所选模型</button>
        </div><div class="small-note">从后端查看并切换 ONNX 模型。由于车道线与目标检测的预/后处理不同，请为两个算法槽位选择兼容模型。</div></div>
        <div class="block edge-device-block" id="edgeDeviceBlock" :class="{ hidden: exp.isSimulation }">
          <label>02 · 边缘主板（设备侧）</label>
          <div class="edge-device-list" role="list" aria-label="近期连接的边缘主板列表">
            <button
              v-for="device in edgeDeviceList"
              :key="device.id"
              class="edge-device"
              :class="{ selected: selectedEdgeDeviceId === device.id }"
              type="button"
              role="listitem"
              :aria-pressed="selectedEdgeDeviceId === device.id"
              @click="selectEdgeDevice(device.id)"
            >
              <span class="edge-device-name">{{ device.name }}</span>
              <span class="device-state" :class="{ online: device.status === 'idle', busy: device.status === 'busy', offline: device.status === 'offline' }">
                <i></i>{{ edgeStatusText(device.status) }}
              </span>
              <span class="edge-device-meta">{{ device.meta || device.id }}<template v-if="device.frames"> · 累计 {{ device.frames }} 帧</template></span>
            </button>
            <div v-if="!edgeDeviceList.length" class="model-item"><b>暂无连接记录</b><span>主板运行客户端后自动出现在这里</span></div>
          </div>
          <div class="edge-connection-bar" :class="{ connected: edgeDeviceConnected && edgeWsConnected }">
            <span>
              <i></i>
              {{ edgeWsConnecting ? "正在连接设备服务…" : edgeDeviceConnected && edgeWsConnected ? `${selectedEdgeDevice.name} 已连接` : selectedEdgeDevice ? `${selectedEdgeDevice.name} 未连接` : "尚未连接主板" }}
            </span>
            <button id="connectEdgeBtn" class="btn btn-primary" :disabled="edgeWsConnecting" @click="reconnectEdge">
              {{ edgeWsConnecting ? "连接中…" : "重连" }}
            </button>
          </div>
          <div class="edge-command-actions">
            <button id="startEdgeDetectionBtn" class="btn btn-soft" :disabled="!edgeDeviceConnected" @click="sendEdgeCommand('start')">开启识别</button>
            <button id="stopEdgeDetectionBtn" class="btn btn-outline" :disabled="!edgeDeviceConnected" @click="sendEdgeCommand('stop')">关闭识别</button>
          </div>
          <div class="edge-stream-stats">
            <span>{{ edgeModelName || "模型未上报" }}</span>
            <span>{{ edgeFps }} fps</span>
            <span>{{ edgeInferMs ? `${edgeInferMs} ms` : "-- ms" }}</span>
            <span v-if="edgeFrameSize.width">{{ edgeFrameSize.width }}×{{ edgeFrameSize.height }}</span>
          </div>
          <div class="small-note">{{ edgeCommandStatus || "以下操作只作用于所选边缘主板，不影响 CARLA 仿真；识别画面实时显示在左侧「AI 感知识别」中。" }}</div>
        </div>
        <div v-if="!exp.isRealScene" class="block"><label>03 · CARLA 车辆</label><select id="vehicleSelect" v-model="exp.vehicleSelection" class="select" :disabled="!exp.canSelectVehicle"><option v-if="!exp.blueprints.length" value="">{{ exp.vehicleHint }}</option><option v-for="blueprint in exp.blueprints" :key="blueprint.id" :value="blueprint.id">{{ blueprint.name }}</option></select></div>
        <div v-if="!exp.isRealScene" class="block"><label>04 · 实验控制</label><div class="side-actions"><button id="createBtn" class="btn btn-primary wide" :disabled="!exp.canCreate" @click="exp.createVehicle()">创建车辆</button><button id="startBtn" class="btn btn-soft" :disabled="!exp.canStart" @click="exp.startDriving()">开始行驶</button><button id="stopBtn" class="btn btn-outline" :disabled="!exp.canStop" @click="exp.stopDriving()">停止行驶</button><button id="destroyBtn" class="btn btn-danger wide" :disabled="!exp.canDestroy" @click="exp.destroyVehicle()">销毁车辆</button></div></div>
        <div class="block"><label>{{ exp.isRealScene ? "03 · 实验记录" : "05 · 实验记录" }}</label><div class="side-actions"><input id="recordNameInput" v-model="recordName" class="select" maxlength="128" placeholder="实验名称（留空自动生成）" style="margin-bottom:8px"><button id="saveRecordBtn" class="btn btn-primary wide" type="button" :disabled="exp.recordSaving" @click="onSaveRecord">{{ exp.recordSaving ? "保存中…" : "结束实验并保存记录" }}</button></div><div class="small-note" id="recordStatus">{{ exp.recordStatus || "实验结束后点击保存，记录会写入数据库并显示在管理端「实验管理」。" }}</div></div>
        <div class="block"><label>运行节点</label><div class="backend-box"><div><b>MODE</b> <span id="runtimeMode">{{ exp.runtimeMode }}</span></div><div><b>WS</b> <span id="wsAddr">{{ exp.isRealScene ? "真实场景不连接 CARLA" : exp.wsAddr }}</span></div><div><b>CARLA</b> {{ exp.isRealScene ? "未启用" : "localhost:2000 @ backend" }}</div><div><b>TM</b> {{ exp.isRealScene ? "未启用" : "port 9000" }}</div></div></div>
      </aside>
      <main class="mainlab">
        <div class="visual-layout" :class="{ stage: exp.isRealScene }">
          <section class="panel" :class="{ 'stage-panel': exp.isRealScene }"><div class="panel-head"><div><b>AI 感知识别</b><span v-if="exp.isRealScene" class="stage-chip" :class="{ live: frontHasFrame }"><i></i>{{ frontHasFrame ? "LIVE" : "STANDBY" }}</span></div><span>{{ exp.isSimulation ? "前视摄像头 · UFLD + YOLO" : "边缘主板 · YOLO · 实时回传" }}</span></div><div class="canvas-wrap"><canvas id="frontCanvas" ref="frontCanvas" :class="{ 'edge-source': !exp.isSimulation }" width="800" height="600"></canvas><div class="empty-state" id="frontEmpty" :class="{ hidden: frontHasFrame }"><div><b>{{ exp.isRealScene ? "等待边缘主板画面" : "等待视觉数据" }}</b>{{ exp.isRealScene ? "主板连接并开启识别后，画面与检测框会显示在这里" : "后端开始推送后显示车道线与目标检测结果" }}</div></div><div class="live-label" id="frontLive" :class="{ on: frontHasFrame }"><i></i>{{ exp.isSimulation ? "PERCEPTION" : "EDGE" }}</div></div><div v-if="exp.isRealScene" class="stage-stats"><div><span>识别模型</span><b>{{ edgeModelName || "--" }}</b></div><div><span>上报帧率</span><b>{{ edgeFps }}<small> fps</small></b></div><div><span>单帧推理</span><b>{{ edgeInferMs ? edgeInferMs : "--" }}<small> ms</small></b></div><div><span>画面分辨率</span><b>{{ edgeFrameSize.width ? `${edgeFrameSize.width}×${edgeFrameSize.height}` : "--" }}</b></div></div></section>
          <div v-if="!exp.isRealScene" class="side-visual-stack">
            <section class="panel"><div class="panel-head"><div><b>CARLA 摄像头画面</b></div><span>第三人称 · Rear Camera</span></div><div class="canvas-wrap"><canvas id="rearCanvas" ref="rearCanvas" width="800" height="600"></canvas><div class="empty-state" id="rearEmpty" :class="{ hidden: rearHasFrame }"><div><b>等待实验启动</b>创建车辆并开始行驶后显示 CARLA 实时画面</div></div><div class="live-label" id="rearLive" :class="{ on: rearHasFrame }"><i></i>CAMERA</div></div></section>
            <div class="compact-metrics"><div class="metric"><span>车辆速度</span><b><em id="speedVal">{{ exp.telemetry.speed }}</em> <small>km/h</small></b><small>CARLA vehicle state</small></div><div class="metric"><span>加速度</span><b><em id="accelVal">{{ exp.telemetry.acceleration }}</em> <small>m/s²</small></b><small>实时状态</small></div><div class="metric"><span>油门</span><b><em id="throttleVal">{{ exp.telemetry.throttle }}</em> <small>%</small></b><small>Autopilot control</small></div><div class="metric"><span>车辆朝向</span><b><em id="yawVal">{{ exp.telemetry.yaw }}</em> <small>°</small></b><small>World yaw</small></div><div class="metric"><span>前视流帧率</span><b><em id="fpsVal">{{ exp.fps }}</em> <small>FPS</small></b><small>浏览器实测</small></div></div>
          </div>
        </div>
        <section class="console"><div class="console-head"><b>Runtime Console</b><span id="consoleModeText">{{ exp.consoleModeText }}</span></div><div class="console-body" id="consoleBody" ref="consoleBody"><div v-for="entry in exp.logs" :key="entry.id" :class="`log-${entry.type}`"><span class="log-time">{{ entry.time }}</span>{{ entry.message }}</div></div></section>
      </main>
    </div>
  </section>
</template>
