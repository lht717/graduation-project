import { resolveWsUrl } from "../ws.js";

export function createWorkspace(api, navigate) {
  let initialized = false;
  let socket = null;
  let vehicleCreated = false;
  let driving = false;
  let creationPending = false;
  let startPending = false;
  let stopPending = false;
  let destroyPending = false;
  let hasBlueprints = false;
  let frameCount = 0;
  let fpsTimer = null;

  const $ = (selector) => document.querySelector(selector);
  const log = (message, type = "normal") => {
    const body = $("#consoleBody");
    const row = document.createElement("div");
    row.className = `log-${type}`;
    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    row.append(time, document.createTextNode(message));
    body.append(row);
    body.scrollTop = body.scrollHeight;
  };
  const setModelStatus = (message, type = "") => {
    const status = $("#modelStatus");
    status.textContent = message;
    status.className = `model-status${type ? ` ${type}` : ""}`;
  };
  const formatBytes = (size) => size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`;
  const isConnected = () => socket?.readyState === WebSocket.OPEN;

  function updateButtons() {
    const connected = isConnected();
    $("#vehicleSelect").disabled = !connected || !hasBlueprints || vehicleCreated;
    $("#createBtn").disabled = !connected || !hasBlueprints || vehicleCreated || creationPending;
    $("#startBtn").disabled = !connected || !vehicleCreated || driving || startPending || stopPending;
    $("#stopBtn").disabled = !connected || !vehicleCreated || !driving || stopPending;
    $("#destroyBtn").disabled = !connected || !vehicleCreated || creationPending || startPending || stopPending || destroyPending;
  }

  function setConnection(connected, message) {
    $("#connectionPill").classList.toggle("ok", connected);
    $("#connectionText").textContent = message;
  }

  function renderModelList(models, active = {}) {
    const library = $("#modelLibrary");
    const ufldSelect = $("#ufldModelSelect");
    const yoloSelect = $("#yoloModelSelect");
    const previousUfld = ufldSelect.value || active.ufld || "";
    const previousYolo = yoloSelect.value || active.yolo || "";
    library.replaceChildren();
    ufldSelect.replaceChildren(new Option("未选择", ""));
    yoloSelect.replaceChildren(new Option("未选择", ""));

    if (!models.length) {
      const empty = document.createElement("div");
      empty.className = "model-item";
      empty.textContent = "暂无可用 ONNX 模型";
      library.append(empty);
    }

    models.forEach((model) => {
      const row = document.createElement("div");
      row.className = "model-item";
      const name = document.createElement("b");
      name.textContent = model.name;
      const roles = (model.active_roles || []).map((role) => role.toUpperCase()).join(" / ");
      const details = document.createElement("span");
      details.textContent = `${roles ? `${roles} · ` : ""}${formatBytes(Number(model.size) || 0)}`;
      row.append(name, details);
      library.append(row);
      ufldSelect.add(new Option(model.name, model.name));
      yoloSelect.add(new Option(model.name, model.name));
    });

    ufldSelect.value = previousUfld;
    yoloSelect.value = previousYolo;
    if (!ufldSelect.value && active.ufld) ufldSelect.value = active.ufld;
    if (!yoloSelect.value && active.yolo) yoloSelect.value = active.yolo;
  }

  async function refreshModels() {
    setModelStatus("正在连接模型服务…");
    try {
      const result = await api.get("/api/models");
      if (!Array.isArray(result.models)) throw new Error("模型列表响应格式无效");
      renderModelList(result.models, result.active || {});
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

  function setMode(mode) {
    const simulation = mode === "simulation";
    $("#simModeBtn").classList.toggle("active", simulation);
    $("#hybridModeBtn").classList.toggle("active", !simulation);
    $("#runtimeMode").textContent = simulation ? "SIMULATION" : "HYBRID";
    $("#workModeLabel").textContent = simulation ? "CARLA · 虚拟仿真" : "CARLA · 虚实结合";
    $("#consoleModeText").textContent = simulation ? "虚拟仿真运行日志" : "虚实结合运行日志";
    $("#edgeDeviceBlock").classList.toggle("hidden", simulation);
    $("#modeNote").textContent = simulation
      ? "通过 WebSocket 与 CARLA 后端建立真实仿真连接。"
      : "边缘设备连接接口尚未接入；CARLA WebSocket 仍连接真实后端。";
    log(`已切换至${simulation ? "虚拟仿真" : "虚实结合"}模式`);
  }

  function drawImageFrame(prefix, bytes) {
    const canvas = prefix === 0 ? $("#frontCanvas") : $("#rearCanvas");
    const empty = prefix === 0 ? $("#frontEmpty") : $("#rearEmpty");
    const live = prefix === 0 ? $("#frontLive") : $("#rearLive");
    const context = canvas.getContext("2d");
    const objectUrl = URL.createObjectURL(new Blob([bytes], { type: "image/jpeg" }));
    const image = new Image();
    image.onload = () => {
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(objectUrl);
      empty.classList.add("hidden");
      live.classList.add("on");
      if (prefix === 0) frameCount += 1;
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      log(`无法解码 ${prefix === 0 ? "AI 感知" : "CARLA"} 图像帧`, "err");
    };
    image.src = objectUrl;
  }

  function updateTelemetry(data) {
    if (!data || typeof data !== "object") return;
    if (Number.isFinite(Number(data.speed))) $("#speedVal").textContent = Number(data.speed).toFixed(0);
    if (Number.isFinite(Number(data.acceleration))) $("#accelVal").textContent = Number(data.acceleration).toFixed(2);
    if (Number.isFinite(Number(data.throttle))) $("#throttleVal").textContent = (Number(data.throttle) * 100).toFixed(0);
    if (Number.isFinite(Number(data.yaw))) $("#yawVal").textContent = Number(data.yaw).toFixed(1);
  }

  function handleTextMessage(text) {
    let message;
    try {
      message = JSON.parse(text);
    } catch (error) {
      log(`后端消息解析失败：${error.message}`, "err");
      return;
    }

    if (message.type === "blueprints") {
      const select = $("#vehicleSelect");
      select.replaceChildren();
      const blueprints = Array.isArray(message.data) ? message.data : [];
      blueprints.forEach((blueprint) => {
        select.add(new Option(blueprint.name, blueprint.id));
      });
      hasBlueprints = blueprints.length > 0;
      if (!hasBlueprints) log("后端未返回可用车辆蓝图", "err");
      else log(`已获取 ${blueprints.length} 个 CARLA 车辆蓝图`, "ok");
      updateButtons();
      return;
    }

    if (message.type === "vehicle_created") {
      creationPending = false;
      vehicleCreated = true;
      $("#vehicleSelect").disabled = true;
      log(`车辆创建成功 · actor_id=${message.vehicle_id}`, "ok");
      updateButtons();
      return;
    }

    if (message.type === "status") {
      if (message.message === "driving_started") {
        startPending = false;
        driving = true;
        log("自动驾驶已启动", "ok");
      } else if (message.message === "driving_stopped") {
        stopPending = false;
        driving = false;
        log("自动驾驶已停止", "warn");
      } else if (message.message === "vehicle_destroyed") {
        destroyPending = false;
        vehicleCreated = false;
        driving = false;
        $("#vehicleSelect").disabled = !isConnected() || !hasBlueprints;
        $("#frontLive").classList.remove("on");
        $("#rearLive").classList.remove("on");
        $("#frontEmpty").classList.remove("hidden");
        $("#rearEmpty").classList.remove("hidden");
        $("#frontCanvas").getContext("2d").clearRect(0, 0, 800, 600);
        $("#rearCanvas").getContext("2d").clearRect(0, 0, 800, 600);
        log("车辆与传感器已销毁", "warn");
      }
      updateTelemetry(message.data);
      updateButtons();
      return;
    }

    if (message.type === "error") {
      creationPending = false;
      startPending = false;
      stopPending = false;
      destroyPending = false;
      log(`后端错误：${message.message || "未知错误"}`, "err");
      updateButtons();
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
    drawImageFrame(prefix, frame.subarray(1));
  }

  function sendAction(action, extra = {}) {
    if (!isConnected()) {
      log("操作失败：WebSocket 后端未连接", "err");
      setConnection(false, "后端未连接");
      updateButtons();
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
      $("#fpsVal").textContent = String(frameCount);
      frameCount = 0;
    }, 1000);
  }

  function connectBackend() {
    if (socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) return;
    const url = resolveWsUrl();
    $("#wsAddr").textContent = url;
    setConnection(false, "正在连接后端…");
    log(`正在连接 WebSocket：${url}`);

    try {
      socket = new WebSocket(url);
      socket.binaryType = "arraybuffer";
    } catch (error) {
      setConnection(false, "后端未连接");
      log(`WebSocket 创建失败：${error.message}`, "err");
      updateButtons();
      return;
    }

    const activeSocket = socket;
    activeSocket.onopen = () => {
      if (socket !== activeSocket) return;
      setConnection(true, "后端已连接");
      log("WebSocket 已连接", "ok");
      updateButtons();
      sendAction("get_vehicle_blueprints");
      startFpsCounter();
    };
    activeSocket.onclose = (event) => {
      if (socket !== activeSocket) return;
      window.clearInterval(fpsTimer);
      fpsTimer = null;
      vehicleCreated = false;
      driving = false;
      creationPending = false;
      startPending = false;
      stopPending = false;
      destroyPending = false;
      hasBlueprints = false;
      $("#vehicleSelect").replaceChildren(new Option("后端未连接", ""));
      $("#vehicleSelect").disabled = true;
      setConnection(false, "后端未连接");
      log(`WebSocket 已断开（code=${event.code}${event.reason ? `，${event.reason}` : ""}）`, "err");
      updateButtons();
    };
    activeSocket.onerror = (event) => {
      if (socket !== activeSocket) return;
      setConnection(false, "后端未连接");
      console.error("WebSocket 连接错误", event);
      log("WebSocket 连接错误：请检查 FastAPI 后端及连接地址", "err");
      updateButtons();
    };
    activeSocket.onmessage = handleMessage;
  }

  function setup() {
    if (initialized) return;
    initialized = true;
    $("#backDashboard").addEventListener("click", () => navigate("dashboard"));
    $("#simModeBtn").addEventListener("click", () => setMode("simulation"));
    $("#hybridModeBtn").addEventListener("click", () => setMode("hybrid"));
    $("#refreshModelsBtn").addEventListener("click", refreshModels);
    $("#modelFileInput").addEventListener("change", () => {
      const file = $("#modelFileInput").files[0];
      $("#uploadModelBtn").disabled = !file;
      if (file) {
        $("#modelSaveName").value = file.name;
        setModelStatus(`已选择 ${file.name} · ${formatBytes(file.size)}`);
      }
    });
    $("#uploadModelBtn").addEventListener("click", async () => {
      const file = $("#modelFileInput").files[0];
      const name = $("#modelSaveName").value.trim();
      if (!file || !name.toLowerCase().endsWith(".onnx")) {
        setModelStatus("请选择 ONNX 文件并填写 .onnx 文件名", "err");
        return;
      }
      const button = $("#uploadModelBtn");
      button.disabled = true;
      setModelStatus(`正在上传 ${name}…`);
      try {
        const result = await api.post(`/api/models/upload?filename=${encodeURIComponent(name)}`, file);
        $("#modelFileInput").value = "";
        $("#modelSaveName").value = "";
        setModelStatus(`模型上传成功：${result.name || name}`, "ok");
        log(`模型上传成功：${result.name || name}`, "ok");
        await refreshModels();
      } catch (error) {
        setModelStatus(`上传失败：${error.message}`, "err");
        log(`模型上传失败：${error.message}`, "err");
      } finally {
        button.disabled = !$("#modelFileInput").files[0];
      }
    });
    $("#loadModelsBtn").addEventListener("click", async () => {
      const ufld = $("#ufldModelSelect").value;
      const yolo = $("#yoloModelSelect").value;
      if (!ufld && !yolo) {
        setModelStatus("请至少选择一个模型", "err");
        return;
      }
      const button = $("#loadModelsBtn");
      button.disabled = true;
      setModelStatus("正在请求后端加载模型…");
      try {
        const result = await api.post("/api/models/load", { ufld_model: ufld || null, yolo_model: yolo || null });
        const active = result.active || {};
        setModelStatus(`模型加载成功：UFLD ${active.ufld || "未加载"} · YOLO ${active.yolo || "未加载"}`, "ok");
        log("后端模型切换成功", "ok");
        await refreshModels();
      } catch (error) {
        setModelStatus(`模型加载失败：${error.message}`, "err");
        log(`模型加载失败：${error.message}`, "err");
      } finally {
        button.disabled = false;
      }
    });
    $("#connectEdgeBtn").disabled = true;
    $("#edgeConnStatus").querySelector("span").textContent = "未接入设备服务";
    $("#createBtn").addEventListener("click", () => {
      if (!hasBlueprints || !isConnected()) return;
      creationPending = sendAction("create_vehicle", { blueprint_id: $("#vehicleSelect").value });
      updateButtons();
    });
    $("#startBtn").addEventListener("click", () => {
      if (!vehicleCreated || !isConnected()) return;
      startPending = sendAction("start_driving");
      updateButtons();
    });
    $("#stopBtn").addEventListener("click", () => {
      if (!vehicleCreated || !driving || !isConnected()) return;
      stopPending = sendAction("stop_driving");
      updateButtons();
    });
    $("#destroyBtn").addEventListener("click", () => {
      if (!vehicleCreated || !isConnected()) return;
      destroyPending = sendAction("destroy_vehicle");
      updateButtons();
    });
    $("#connectionPill").classList.remove("ok");
    setConnection(false, "后端未连接");
    updateButtons();
  }

  return {
    activate() {
      setup();
      void refreshModels();
      connectBackend();
    }
  };
}
