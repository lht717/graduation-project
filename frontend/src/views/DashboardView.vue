<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { get } from "@/api/client.js";

defineOptions({ name: "DashboardView" });

const router = useRouter();

// 内置三个实验的展示文案，让数据库里的默认类型保持原样；
// 其余（管理员在「实验类型」页新增的）类型默认「规划中」，不开放进入。
const CARD_PRESETS = {
  "智能汽车视觉感知实验": {
    badge: "可运行 · 双模式",
    description: "CARLA 城市道路 · UFLD 车道线检测 · YOLO 目标检测 · 自动驾驶状态监控",
    chips: ["CARLA", "ONNX Runtime", "WebSocket"],
    art: "city",
    active: true
  },
  "仓储 AGV 实验": {
    badge: "规划中",
    description: "将在后续场景适配阶段开放。",
    chips: ["AGV", "Warehouse"],
    art: "plain",
    active: false
  },
  "巡检机器人实验": {
    badge: "规划中",
    description: "将在机器人仿真适配完成后开放。",
    chips: ["Robot", "Patrol"],
    art: "plain",
    active: false
  }
};

// 后端未重启 / 接口不可用时的兜底数据，保证实验中心不会空白
const FALLBACK_TYPES = [
  { id: "default-1", name: "智能汽车视觉感知实验", sort_order: 1, remark: "", created_at: "" },
  { id: "default-2", name: "仓储 AGV 实验", sort_order: 2, remark: "", created_at: "" },
  { id: "default-3", name: "巡检机器人实验", sort_order: 3, remark: "", created_at: "" }
];

const TYPE_CACHE_KEY = "fusionlab_experiment_types";

const types = ref([...FALLBACK_TYPES]);
const loading = ref(false);
const loaded = ref(false);
const errorMessage = ref("");
const source = ref("default"); // api | cache | stale | default

function readCachedTypes() {
  try {
    const raw = localStorage.getItem(TYPE_CACHE_KEY);
    const rows = raw ? JSON.parse(raw) : null;
    return Array.isArray(rows) && rows.length ? rows : null;
  } catch {
    return null;
  }
}

function shortChip(text) {
  const value = String(text || "").trim();
  return value.length > 14 ? `${value.slice(0, 14)}…` : value;
}

function chipsFromRemark(remark, createdAt) {
  const parts = String(remark || "")
    .split(/[·、,，;；/|\n]+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 3)
    .map(shortChip);
  if (parts.length) return parts;
  const created = String(createdAt || "").slice(0, 10);
  return ["自定义实验", created ? `创建于 ${created}` : "CARLA 工作台"];
}

const cards = computed(() =>
  types.value.map((row, index) => {
    const name = String(row.name || "").trim();
    const preset = CARD_PRESETS[name];
    if (preset) return { key: row.id ?? name, name, ...preset, index, isNew: false };
    return {
      key: row.id ?? name,
      name,
      // 新增类型默认规划中：显示备注与标签，但按钮为「暂未开放」且不可点击
      badge: "规划中",
      description: String(row.remark || "").trim() || "该实验类型暂未开放，将在后续场景适配完成后开放。",
      chips: chipsFromRemark(row.remark, row.created_at),
      art: "new",
      active: false,
      isNew: true,
      index,
      glyph: Array.from(name)[0] || "实",
      hue: index % 4
    };
  })
);

async function fetchTypes() {
  try {
    const result = await get("/api/experiment-types");
    if (!Array.isArray(result.experiment_types)) throw new Error("实验类型列表格式不正确");
    return result.experiment_types;
  } catch (error) {
    // 后端尚未重启（公开接口 404）或接口异常时，管理员账号可用管理端接口兜底
    if (error?.status === 401 || error?.status === 403) throw error;
    try {
      const fallback = await get("/api/admin/experiment-types");
      if (!Array.isArray(fallback.experiment_types)) throw error;
      return fallback.experiment_types;
    } catch {
      throw error;
    }
  }
}

async function loadTypes() {
  loading.value = true;
  try {
    types.value = await fetchTypes();
    loaded.value = true;
    errorMessage.value = "";
    source.value = "api";
  } catch (error) {
    errorMessage.value = error?.message || "未知错误";
    const cached = readCachedTypes();
    if (cached) {
      types.value = cached;
      loaded.value = true;
      source.value = "cache";
    } else if (!loaded.value) {
      types.value = [...FALLBACK_TYPES];
      source.value = "default";
    } else {
      source.value = "stale";
    }
  } finally {
    loading.value = false;
  }
}

function openExperiment(card) {
  if (!card.active) return;
  router.push({ path: "/workspace", query: { type: card.name } });
}

onMounted(() => {
  void loadTypes();
});
</script>

<template>
  <section id="dashboardView">
    <main class="container">
      <div class="dashboard-head">
        <div>
          <div class="eyebrow">MY EXPERIMENTS</div>
          <h1>实验中心</h1>
          <p>选择一个实验进入工作台。实验工作台支持虚拟仿真与虚实结合两种运行模式。</p>
        </div>
        <div class="dashboard-head-tools">
          <span class="exp-type-count">共 {{ cards.length }} 个实验类型</span>
          <button class="exp-type-refresh" type="button" :disabled="loading" @click="loadTypes">
            {{ loading ? "加载中…" : "↻ 刷新" }}
          </button>
        </div>
      </div>

      <p v-if="errorMessage" class="exp-type-hint" role="status">
        实验类型接口暂不可用（{{ errorMessage }}），{{
          source === "cache"
            ? "当前显示本机缓存的分类"
            : source === "stale"
              ? "当前显示上次加载的列表"
              : "当前显示默认实验列表"
        }}。重启后端后点「刷新」即可从数据库同步。
      </p>

      <div class="experiment-grid">
        <article
          v-for="card in cards"
          :key="card.key"
          :class="['exp-card', card.active ? 'active-card' : 'coming', { 'exp-card-new': card.isNew }]"
        >
          <div
            :class="[
              'exp-art',
              card.art === 'city' ? 'city' : '',
              card.art === 'new' ? `exp-art-new exp-art-hue-${card.hue}` : ''
            ]"
          >
            <span class="exp-badge">{{ card.badge }}</span>
            <span v-if="card.isNew" class="exp-art-glyph" aria-hidden="true">{{ card.glyph }}</span>
          </div>
          <div class="exp-body">
            <h3 :title="card.name">{{ card.name }}</h3>
            <p :title="card.description">{{ card.description }}</p>
            <div class="exp-meta">
              <span v-for="(chip, chipIndex) in card.chips" :key="`${card.key}-${chipIndex}`" class="chip" :title="chip">{{ chip }}</span>
            </div>
            <button
              v-if="card.active"
              class="btn btn-primary"
              type="button"
              @click="openExperiment(card)"
            >进入实验</button>
            <button v-else class="btn btn-outline" type="button" disabled>暂未开放</button>
          </div>
        </article>
        <p v-if="loaded && !cards.length" class="exp-type-empty">
          暂无实验类型，请联系管理员在「实验类型」中添加。
        </p>
      </div>
    </main>
  </section>
</template>
