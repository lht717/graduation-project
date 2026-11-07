import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { get, post } from "@/api/client.js";
import { resolveWsUrl } from "@/ws/url.js";

function formatBytes(size) {
  return size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`;
}

let logId = 0;

export const useExperimentStore = defineStore("experiment", () => {
  /* ---------------- 连接与车辆状态 ---------------- */
  let socket = null;
  let fpsTimer = null;
  let frameCount = 0;
  let frameHandler = null;
  // 实验计时：driving_started 起算，driving_stopped 累加
  let drivingStartedAt = null;
  let accumulatedSeconds = 0;

  const connected = ref(false);
  const connectionText = ref("后端未连接");
  const wsAddr = ref("等待连接");

  const vehicleCreated = ref(false);
  const driving = ref(false);
  const creationPending = ref(false);
  const startPending = ref(false);
  const stopPending = ref(false);
  const destroyPending = ref(false);
  const hasBlueprints = ref(false);

  const blueprints = ref([]);
  const vehicleSelection = ref("");
  // 原版下拉框的占位项文案：初始「等待后端车辆蓝图…」，断开后变成「后端未连接」
  const vehicleHint = ref("等待后端车辆蓝图…");
  // 收到 vehicle_destroyed 时视图需要清空两路画面
  const frameResetTick = ref(0);

  /* ---------------- 运行模式 ---------------- */
  const mode = ref("simulation");
  const modeTouched = ref(false);

  /* ---------------- 遥测与帧率 ---------------- */
  const telemetry = ref({ speed: "0", acceleration: "0.00", throttle: "0", yaw: "0.0" });
  const fps = ref(0);

  /* ---------------- 模型库 ---------------- */
  const models = ref([]);
  const modelStatus = ref("模型将从后端加载。");
  const modelStatusState = ref("");
  const activeModels = ref({});
  const ufldSelection = ref("");
  const yoloSelection = ref("");
  const modelsLoading = ref(false);
  // 区分「还没拉过」与「拉过但为空」，对应原版初始的「正在读取模型库...」
  const modelsLoaded = ref(false);

  /* ---------------- 控制台日志 ---------------- */
  const logs = ref([]);

  /* ---------------- 实验记录保存 ---------------- */
  const recordSaving = ref(false);
  const recordStatus = ref("");

  /* ---------------- 派生状态（对应原版 updateButtons） ---------------- */
  const canSelectVehicle = computed(() => connected.value && hasBlueprints.value && !vehicleCreated.value);
  const canCreate = computed(
    () => connected.value && hasBlueprints.value && !vehicleCreated.value && !creationPending.value
  );
  const canStart = computed(
    () =>
      connected.value &&
      vehicleCreated.value &&
      !driving.value &&
      !startPending.value &&
      !stopPending.value
  );
  const canStop = computed(() => connected.value && vehicleCreated.value && driving.value && !stopPending.value);
  const canDestroy = computed(
    () =>
      connected.value &&
      vehicleCreated.value &&
      !creationPending.value &&
      !startPending.value &&
      !stopPending.value &&
      !destroyPending.value
  );

  const isSimulation = computed(() => mode.value === "simulation");
  const workModeLabel = computed(() => (isSimulation.value ? "CARLA · 虚拟仿真" : "CARLA · 虚实结合"));
  const runtimeMode = computed(() => (isSimulation.value ? "SIMULATION" : "HYBRID"));
  const modeNote = computed(() =>
    isSimulation.value
      ? "通过 WebSocket 与 CARLA 后端建立真实仿真连接。"
      : "边缘设备连接接口尚未接入；CARLA WebSocket 仍连接真实后端。"
  );
  // 原版 HTML 里的初始文案是「实验运行日志」，首次点击模式切换后才变成对应的运行日志
  const consoleModeText = computed(() => {
    if (!modeTouched.value) return "实验运行日志";
    return isSimulation.value ? "虚拟仿真运行日志" : "虚实结合运行日志";
  });

  /* ---------------- 基础动作 ---------------- */
  function log(message, type = "normal") {
    logs.value.push({
      id: (logId += 1),
      time: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
      message,
      type
    });
  }

  function setModelStatus(message, type = "") {
    modelStatus.value = message;
    modelStatusState.value = type;
  }

  function setConnection(next, message) {
    connected.value = next;
    connectionText.value = message;
  }

  const isConnected = () => socket?.readyState === WebSocket.OPEN;

  function countFrame() {
    frameCount += 1;
  }

  /* ---------------- 模型库 ---------------- */
  function renderModelList(list, active = {}) {
    const previousUfld = ufldSelection.value || active.ufld || "";
    const previousYolo = yoloSelection.value || active.yolo || "";
    models.value = Array.isArray(list) ? list : [];
    modelsLoaded.value = true;
    ufldSelection.value = previousUfld;
    yoloSelection.value = previousYolo;
    if (!ufldSelection.value && active.ufld) ufldSelection.value = active.ufld;
    if (!yoloSelection.value && active.yolo) yoloSelection.value = active.yolo;
  }

  async function refreshModels() {
    setModelStatus("正在连接模型服务…");
    try {
      const result = await get("/api/models");
      if (!Array.isArray(result.models)) throw new Error("模型列表响应格式无效");
      renderModelList(result.models, result.active || {});
      activeModels.value = result.active || {};
      setModelStatus(
        result.models.length ? `已从后端加载 ${result.models.length} 个模型` : "后端模型库为空",
        result.models.length ? "ok" : ""
      );
    } catch (error) {
      renderModelList([]);
      setModelStatus(`模型服务连接失败：${error.message}`, "err");
      log(`模型服务连接失败：${error.message}`, "err");
    }
  }

  function setMode(next) {
    mode.value = next;
    modeTouched.value = true;
    log(`已切换至${next === "simulation" ? "虚拟仿真" : "虚实结合"}模式`);
  }

  async function uploadModel(file, name) {
    if (!file || !String(name).toLowerCase().endsWith(".onnx")) {
      setModelStatus("请选择 ONNX 文件并填写 .onnx 文件名", "err");
      return false;
    }
    setModelStatus(`正在上传 ${name}…`);
    try {
      const result = await post(`/api/models/upload?filename=${encodeURIComponent(name)}`, file);
      setModelStatus(`模型上传成功：${result.name || name}`, "ok");
      log(`模型上传成功：${result.name || name}`, "ok");
      await refreshModels();
      return true;
    } catch (error) {
      setModelStatus(`上传失败：${error.message}`, "err");
      log(`模型上传失败：${error.message}`, "err");
      return false;
    }
  }

  async function loadSelectedModels() {
    const ufld = ufldSelection.value;
    const yolo = yoloSelection.value;
    if (!ufld && !yolo) {
      setModelStatus("请至少选择一个模型", "err");
      return false;
    }
    setModelStatus("正在请求后端加载模型…");
    try {
      const result = await post("/api/models/load", {
        ufld_model: ufld || null,
        yolo_model: yolo || null
      });
      const active = result.active || {};
      setModelStatus(`模型加载成功：UFLD ${active.ufld || "未加载"} · YOLO ${active.yolo || "未加载"}`, "ok");
      log("后端模型切换成功", "ok");
      await refreshModels();
      return true;
    } catch (error) {
      setModelStatus(`模型加载失败：${error.message}`, "err");
      log(`模型加载失败：${error.message}`, "err");
      return false;
    }
  }

  /* ---------------- 遥测 ---------------- */
  function updateTelemetry(data) {
    if (!data || typeof data !== "object") return;
    const next = { ...telemetry.value };
    if (Number.isFinite(Number(data.speed))) next.speed = Number(data.speed).toFixed(0);
    if (Number.isFinite(Number(data.acceleration))) next.acceleration = Number(data.acceleration).toFixed(2);
    if (Number.isFinite(Number(data.throttle))) next.throttle = (Number(data.throttle) * 100).toFixed(0);
    if (Number.isFinite(Number(data.yaw))) next.yaw = Number(data.yaw).toFixed(1);
    telemetry.value = next;
  }

  /* ---------------- 实验记录保存 ---------------- */
  async function saveExperimentRecord(name = "", experimentType = "") {
    recordSaving.value = true;
    recordStatus.value = "正在保存实验记录…";
    try {
      const payload = {
        name: String(name || "").trim(),
        experiment_type: String(experimentType || "").trim(),
        duration_seconds: currentDurationSeconds(),
        speed: Number(telemetry.value.speed) || 0,
        acceleration: Number(telemetry.value.acceleration) || 0,
        throttle: Number(telemetry.value.throttle) || 0,
        yaw: Number(telemetry.value.yaw) || 0,
        front_fps: Number(fps.value) || 0
      };
      if (!payload.experiment_type) throw new Error("无法识别当前实验类型");
      const result = await post("/api/experiments", payload);
      recordStatus.value = `已写入数据库：${result.experiment?.name || payload.name}`;
      log(`实验记录已保存（id=${result.experiment?.id ?? "?"}）`, "ok");
      resetTimer();
      return true;
    } catch (error) {
      recordStatus.value = `保存失败：${error.message}`;
      log(`保存实验记录失败：${error.message}`, "err");
      return false;
    } finally {
      recordSaving.value = false;
    }
  }

  /* ---------------- 实验计时 ---------------- */
  function stopTimer() {
    if (drivingStartedAt !== null) {
      accumulatedSeconds += Math.max(0, (Date.now() - drivingStartedAt) / 1000);
      drivingStartedAt = null;
    }
  }

  function currentDurationSeconds() {
    const running = drivingStartedAt !== null ? (Date.now() - drivingStartedAt) / 1000 : 0;
    return Math.round(accumulatedSeconds + running);
  }

  function resetTimer() {
    drivingStartedAt = null;
    accumulatedSeconds = 0;
  }

  /* ---------------- 消息处理 ---------------- */
  function handleTextMessage(text) {
    let message;
    try {
      message = JSON.parse(text);
    } catch (error) {
      log(`后端消息解析失败：${error.message}`, "err");
      return;
    }

    if (message.type === "blueprints") {
      const list = Array.isArray(message.data) ? message.data : [];
      blueprints.value = list;
      vehicleSelection.value = list.length ? list[0].id : "";
      hasBlueprints.value = list.length > 0;
      if (!hasBlueprints.value) log("后端未返回可用车辆蓝图", "err");
      else log(`已获取 ${list.length} 个 CARLA 车辆蓝图`, "ok");
      return;
    }

    if (message.type === "vehicle_created") {
      creationPending.value = false;
      vehicleCreated.value = true;
      log(`车辆创建成功 · actor_id=${message.vehicle_id}`, "ok");
      return;
    }

    if (message.type === "status") {
      if (message.message === "driving_started") {
        startPending.value = false;
        driving.value = true;
        drivingStartedAt = Date.now();
        log("自动驾驶已启动", "ok");
      } else if (message.message === "driving_stopped") {
        stopPending.value = false;
        driving.value = false;
        stopTimer();
        log("自动驾驶已停止", "warn");
      } else if (message.message === "vehicle_destroyed") {
        destroyPending.value = false;
        vehicleCreated.value = false;
        driving.value = false;
        stopTimer();
        frameResetTick.value += 1;
        log("车辆与传感器已销毁", "warn");
      }
      updateTelemetry(message.data);
      return;
    }

    if (message.type === "error") {
      creationPending.value = false;
      startPending.value = false;
      stopPending.value = false;
      destroyPending.value = false;
      log(`后端错误：${message.message || "未知错误"}`, "err");
    }
  }

  function handleMessage(event) {
    if (typeof event.data === "string") {
      handleTextMessage(event.data);
      return;
    }
    if (!(event.data instanceof ArrayBuffer)) {
      log("收到不支持的 WebSocket 消息类型", "err");
      return;
    }
    const frame = new Uint8Array(event.data);
    if (frame.length < 2) {
      log("收到无效的图像帧", "err");
      return;
    }
    const prefix = frame[0];
    if (prefix !== 0 && prefix !== 1) {
      log(`收到未知图像帧前缀：${prefix}`, "err");
      return;
    }
    if (frameHandler) frameHandler(prefix, frame.subarray(1));
  }

  function sendAction(action, extra = {}) {
    if (!isConnected()) {
      log("操作失败：WebSocket 后端未连接", "err");
      setConnection(false, "后端未连接");
      return false;
    }
    try {
      socket.send(JSON.stringify({ action, ...extra }));
      return true;
    } catch (error) {
      log(`发送 ${action} 失败：${error.message}`, "err");
      return false;
    }
  }

  function startFpsCounter() {
    window.clearInterval(fpsTimer);
    fpsTimer = window.setInterval(() => {
      fps.value = frameCount;
      frameCount = 0;
    }, 1000);
  }

  function connectBackend() {
    if (socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) return;
    const url = resolveWsUrl();
    wsAddr.value = url;
    setConnection(false, "正在连接后端…");
    log(`正在连接 WebSocket：${url}`);

    try {
      socket = new WebSocket(url);
      socket.binaryType = "arraybuffer";
    } catch (error) {
      setConnection(false, "后端未连接");
      log(`WebSocket 创建失败：${error.message}`, "err");
      return;
    }

    const activeSocket = socket;
    activeSocket.onopen = () => {
      if (socket !== activeSocket) return;
      setConnection(true, "后端已连接");
      log("WebSocket 已连接", "ok");
      sendAction("get_vehicle_blueprints");
      startFpsCounter();
    };
    activeSocket.onclose = (event) => {
      if (socket !== activeSocket) return;
      window.clearInterval(fpsTimer);
      fpsTimer = null;
      stopTimer();
      vehicleCreated.value = false;
      driving.value = false;
      creationPending.value = false;
      startPending.value = false;
      stopPending.value = false;
      destroyPending.value = false;
      hasBlueprints.value = false;
      blueprints.value = [];
      vehicleSelection.value = "";
      vehicleHint.value = "后端未连接";
      setConnection(false, "后端未连接");
      log(`WebSocket 已断开（code=${event.code}${event.reason ? `，${event.reason}` : ""}）`, "err");
    };
    activeSocket.onerror = (event) => {
      if (socket !== activeSocket) return;
      setConnection(false, "后端未连接");
      console.error("WebSocket 连接错误", event);
      log("WebSocket 连接错误：请检查 FastAPI 后端及连接地址", "err");
    };
    activeSocket.onmessage = handleMessage;
  }

  /* ---------------- 车辆操作 ---------------- */
  function createVehicle() {
    if (!hasBlueprints.value || !isConnected()) return;
    creationPending.value = sendAction("create_vehicle", { blueprint_id: vehicleSelection.value });
  }

  function startDriving() {
    if (!vehicleCreated.value || !isConnected()) return;
    startPending.value = sendAction("start_driving");
  }

  function stopDriving() {
    if (!vehicleCreated.value || !driving.value || !isConnected()) return;
    stopPending.value = sendAction("stop_driving");
  }

  function destroyVehicle() {
    if (!vehicleCreated.value || !isConnected()) return;
    destroyPending.value = sendAction("destroy_vehicle");
  }

  /* ---------------- 帧处理注册 ---------------- */
  function setFrameHandler(handler) {
    frameHandler = handler;
  }

  /** 原版 showView('workspace') → workspace.activate() */
  function activate() {
    void refreshModels();
    connectBackend();
  }

  /** 卸载时断开（原版页面关闭才发生） */
  function disconnect() {
    window.clearInterval(fpsTimer);
    fpsTimer = null;
    if (socket) {
      socket.onopen = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      try {
        socket.close();
      } catch {
        /* ignore */
      }
      socket = null;
    }
    setConnection(false, "后端未连接");
  }

  return {
    connected,
    connectionText,
    wsAddr,
    vehicleCreated,
    driving,
    creationPending,
    startPending,
    stopPending,
    destroyPending,
    hasBlueprints,
    blueprints,
    vehicleSelection,
    vehicleHint,
    frameResetTick,
    mode,
    telemetry,
    fps,
    models,
    modelStatus,
    modelStatusState,
    activeModels,
    ufldSelection,
    yoloSelection,
    modelsLoading,
    modelsLoaded,
    logs,
    recordSaving,
    recordStatus,
    saveExperimentRecord,
    currentDurationSeconds,
    canSelectVehicle,
    canCreate,
    canStart,
    canStop,
    canDestroy,
    isSimulation,
    workModeLabel,
    runtimeMode,
    modeNote,
    consoleModeText,
    log,
    setModelStatus,
    refreshModels,
    setMode,
    uploadModel,
    loadSelectedModels,
    countFrame,
    setFrameHandler,
    createVehicle,
    startDriving,
    stopDriving,
    destroyVehicle,
    activate,
    disconnect,
    formatBytes
  };
});
