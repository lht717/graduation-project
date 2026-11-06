<script setup>
import { nextTick, onActivated, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useExperimentStore } from "@/stores/experiment.js";

defineOptions({ name: "WorkspaceView" });

const exp = useExperimentStore();
const router = useRouter();

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

async function onSaveRecord() {
  await exp.saveExperimentRecord(recordName.value);
}

const pendingObjectUrls = new Set();

/* ---------------- 帧绘制（对应原版 drawImageFrame） ---------------- */
function drawFrame(prefix, bytes) {
  const canvas = prefix === 0 ? frontCanvas.value : rearCanvas.value;
  if (!canvas) return;
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
onActivated(() => {
  exp.activate();
});

onUnmounted(() => {
  exp.setFrameHandler(null);
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
        <div class="work-title"><b>智能汽车视觉感知实验</b><span id="workModeLabel">{{ exp.workModeLabel }}</span></div>
      </div>
    </header>
    <div class="work-body">
      <aside class="sidebar">
        <div class="side-head">实验配置</div>
        <div class="block"><label>01 · 运行模式</label><div class="mode-tabs"><button id="simModeBtn" :class="{ active: exp.isSimulation }" @click="exp.setMode('simulation')">虚拟仿真</button><button id="hybridModeBtn" :class="{ active: !exp.isSimulation }" @click="exp.setMode('hybrid')">虚实结合</button></div><div class="small-note" id="modeNote">{{ exp.modeNote }}</div></div>
        <div class="block"><label>02 · AI 模型库</label><div class="model-box">
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
        <div class="block" id="edgeDeviceBlock" :class="{ hidden: exp.isSimulation }"><label>03 · 边缘主板</label><div class="edge-connect-row"><div class="edge-conn-status" id="edgeConnStatus"><i></i><span>未接入设备服务</span></div><button id="connectEdgeBtn" class="btn btn-primary" disabled>连接</button></div><div class="small-note">边缘设备服务接口尚未接入。</div></div>
        <div class="block"><label>04 · CARLA 车辆</label><select id="vehicleSelect" v-model="exp.vehicleSelection" class="select" :disabled="!exp.canSelectVehicle"><option v-if="!exp.blueprints.length" value="">{{ exp.vehicleHint }}</option><option v-for="blueprint in exp.blueprints" :key="blueprint.id" :value="blueprint.id">{{ blueprint.name }}</option></select></div>
        <div class="block"><label>05 · 实验控制</label><div class="side-actions"><button id="createBtn" class="btn btn-primary wide" :disabled="!exp.canCreate" @click="exp.createVehicle()">创建车辆</button><button id="startBtn" class="btn btn-soft" :disabled="!exp.canStart" @click="exp.startDriving()">开始行驶</button><button id="stopBtn" class="btn btn-outline" :disabled="!exp.canStop" @click="exp.stopDriving()">停止行驶</button><button id="destroyBtn" class="btn btn-danger wide" :disabled="!exp.canDestroy" @click="exp.destroyVehicle()">销毁车辆</button></div></div>
        <div class="block"><label>06 · 实验记录</label><div class="side-actions"><input id="recordNameInput" v-model="recordName" class="select" maxlength="128" placeholder="实验名称（留空自动生成）" style="margin-bottom:8px"><button id="saveRecordBtn" class="btn btn-primary wide" type="button" :disabled="exp.recordSaving" @click="onSaveRecord">{{ exp.recordSaving ? "保存中…" : "结束实验并保存记录" }}</button></div><div class="small-note" id="recordStatus">{{ exp.recordStatus || "实验结束后点击保存，记录会写入数据库并显示在管理端「实验管理」。" }}</div></div>
        <div class="block"><label>运行节点</label><div class="backend-box"><div><b>MODE</b> <span id="runtimeMode">{{ exp.runtimeMode }}</span></div><div><b>WS</b> <span id="wsAddr">{{ exp.wsAddr }}</span></div><div><b>CARLA</b> localhost:2000 @ backend</div><div><b>TM</b> port 9000</div></div></div>
      </aside>
      <main class="mainlab">
        <div class="visual-layout">
          <section class="panel"><div class="panel-head"><div><b>AI 感知识别</b></div><span>前视摄像头 · UFLD + YOLO</span></div><div class="canvas-wrap"><canvas id="frontCanvas" ref="frontCanvas" width="800" height="600"></canvas><div class="empty-state" id="frontEmpty" :class="{ hidden: frontHasFrame }"><div><b>等待视觉数据</b>后端开始推送后显示车道线与目标检测结果</div></div><div class="live-label" id="frontLive" :class="{ on: frontHasFrame }"><i></i>PERCEPTION</div></div></section>
          <div class="side-visual-stack">
            <section class="panel"><div class="panel-head"><div><b>CARLA 摄像头画面</b></div><span>第三人称 · Rear Camera</span></div><div class="canvas-wrap"><canvas id="rearCanvas" ref="rearCanvas" width="800" height="600"></canvas><div class="empty-state" id="rearEmpty" :class="{ hidden: rearHasFrame }"><div><b>等待实验启动</b>创建车辆并开始行驶后显示 CARLA 实时画面</div></div><div class="live-label" id="rearLive" :class="{ on: rearHasFrame }"><i></i>CAMERA</div></div></section>
            <div class="compact-metrics"><div class="metric"><span>车辆速度</span><b><em id="speedVal">{{ exp.telemetry.speed }}</em> <small>km/h</small></b><small>CARLA vehicle state</small></div><div class="metric"><span>加速度</span><b><em id="accelVal">{{ exp.telemetry.acceleration }}</em> <small>m/s²</small></b><small>实时状态</small></div><div class="metric"><span>油门</span><b><em id="throttleVal">{{ exp.telemetry.throttle }}</em> <small>%</small></b><small>Autopilot control</small></div><div class="metric"><span>车辆朝向</span><b><em id="yawVal">{{ exp.telemetry.yaw }}</em> <small>°</small></b><small>World yaw</small></div><div class="metric"><span>前视流帧率</span><b><em id="fpsVal">{{ exp.fps }}</em> <small>FPS</small></b><small>浏览器实测</small></div></div>
          </div>
        </div>
        <section class="console"><div class="console-head"><b>Runtime Console</b><span id="consoleModeText">{{ exp.consoleModeText }}</span></div><div class="console-body" id="consoleBody" ref="consoleBody"><div v-for="entry in exp.logs" :key="entry.id" :class="`log-${entry.type}`"><span class="log-time">{{ entry.time }}</span>{{ entry.message }}</div></div></section>
      </main>
    </div>
  </section>
</template>
