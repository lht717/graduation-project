<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { unzipSync, strFromU8 } from "fflate";
import { get, patch, post, put, remove } from "@/api/client.js";
import { useAuthStore } from "@/stores/auth.js";

defineOptions({ name: "AdminView" });

const router = useRouter();
const auth = useAuthStore();
const adminSection = ref("dashboard");
const lastRefreshed = ref(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }));
const dashboardStatus = ref("");
const sectionTitles = {
  dashboard: "学习看板",
  users: "学生管理",
  classes: "班级管理",
  roles: "角色管理",
  courses: "课程管理",
  experiments: "实验管理",
  experimentTypes: "实验类型",
  basics: "基础信息"
};
const sectionTitle = computed(() => sectionTitles[adminSection.value] || "学习看板");
const recentSectionStorageKey = "fusionlab_admin_recent_sections";
const recentSectionLimit = 5;
const adminSectionMeta = {
  dashboard: { icon: "看", tone: "quick-blue" },
  users: { icon: "学", tone: "quick-green" },
  classes: { icon: "班", tone: "quick-orange" },
  roles: { icon: "权", tone: "quick-violet" },
  experiments: { icon: "验", tone: "quick-violet" },
  experimentTypes: { icon: "类", tone: "quick-blue" }
};

function loadRecentSections() {
  const storedSections = localStorage.getItem(recentSectionStorageKey);
  if (!storedSections) return [];
  try {
    const sections = JSON.parse(storedSections);
    return Array.isArray(sections)
      ? sections.filter((section) => Object.hasOwn(adminSectionMeta, section)).slice(0, recentSectionLimit)
      : [];
  } catch (error) {
    console.warn("无法读取最近访问的管理页面记录。", error);
    localStorage.removeItem(recentSectionStorageKey);
    return [];
  }
}

const recentSections = ref(loadRecentSections());
const recentSectionLinks = computed(() =>
  recentSections.value.map((section) => ({
    id: section,
    title: sectionTitles[section],
    ...adminSectionMeta[section]
  }))
);

const experimentTotal = ref(null);
const dashboardExperimentsLoading = ref(false);
const dashboardExperimentsError = ref("");
const studentTotal = ref(null);
const stats = computed(() => [
  { label: "实验", value: experimentTotal.value ?? "—", tone: "violet", icon: "验" },
  { label: "学生", value: studentTotal.value ?? "—", tone: "green", icon: "学" }
]);
const recentExperiments = ref([]);

const users = ref([]);
const usersStatus = ref("");
const usersStatusState = ref("");
const studentIdFilter = ref("");
const studentNameFilter = ref("");
const appliedStudentId = ref("");
const appliedStudentName = ref("");
const selectedStudentUsernames = ref([]);
const studentBatchDeleting = ref(false);
const studentBatchEditOpen = ref(false);
const studentBatchEditing = ref(false);
const studentBatchEditUsernames = ref([]);
const studentBatchEditError = ref("");
const studentBatchChangeClass = ref(false);
const studentBatchResetPassword = ref(false);
const studentBatchClassName = ref("");
const studentBatchGrade = ref("");
const studentBatchNewPassword = ref("");
const selectedClassName = ref("");
const classListSearch = ref("");
const studentImportInput = ref(null);
const importingStudents = ref(false);
const showStudentColumnSettings = ref(false);
const compactStudentTable = ref(false);
const studentColumns = ref([
  { key: "account_id", label: "学号", visible: true },
  { key: "display_name", label: "姓名", visible: true },
  { key: "class_name", label: "所属班级", visible: true },
  { key: "grade", label: "年级", visible: true },
  { key: "status", label: "状态", visible: true },
  { key: "registered_at", label: "创建时间", visible: true }
]);
const classes = ref([]);
const classNameFilter = ref("");
const classGradeFilter = ref("");
const classesStatus = ref("");
const classesStatusState = ref("");
const classesLoading = ref(false);
const classFormOpen = ref(false);
const classSaving = ref(false);
const classEditingId = ref(null);
const classActionId = ref(null);
const classForm = ref({ name: "", grade: "", student_count: 0, sort_order: 0, remark: "" });
const classColumnOptions = ref([
  { key: "name", label: "班级名称", visible: true },
  { key: "grade", label: "年级", visible: true },
  { key: "student_count", label: "人数", visible: true },
  { key: "sort_order", label: "排序", visible: true },
  { key: "created_at", label: "创建时间", visible: true },
  { key: "remark", label: "备注", visible: true }
]);
const showClassColumnSettings = ref(false);
const compactClassTable = ref(false);
const experiments = ref([]);
const experimentKeyword = ref("");
const experimentStatus = ref("");
const experimentStatusState = ref("");
const experimentLoading = ref(false);
const experimentPage = ref(1);
const experimentPageSize = 10;
const selectedExperimentIds = ref([]);
const experimentBatchDeleting = ref(false);
const experimentTypes = ref([]);
const experimentTypeFilter = ref("");
const experimentFormOpen = ref(false);
const experimentSaving = ref(false);
const experimentEditingId = ref(null);
const experimentActionId = ref(null);
const experimentToView = ref(null);
const experimentForm = ref({
  name: "",
  experiment_type: "",
  description: ""
});

// 实验类型管理
const typeRecords = ref([]);
const typeStatus = ref("");
const typeStatusState = ref("");
const typeLoading = ref(false);
const typeFormOpen = ref(false);
const typeSaving = ref(false);
const typeEditingId = ref(null);
const typeActionId = ref(null);
const typeImportInput = ref(null);
const importingTypes = ref(false);
const showTypeExportMenu = ref(false);
const showTypeSettings = ref(false);
const compactTypeTable = ref(false);
const typeForm = ref({ name: "", sort_order: 0, remark: "" });

// 实验中心读取的兜底缓存：后端未重启 / 公开接口暂不可用时也能显示最新分类
const TYPE_CACHE_KEY = "fusionlab_experiment_types";
watch(
  typeRecords,
  (rows) => {
    try {
      localStorage.setItem(TYPE_CACHE_KEY, JSON.stringify(rows));
    } catch {
      /* 隐私模式或存储不可用时忽略 */
    }
  },
  { deep: true }
);

const typeColumns = ref([
  { key: "name", label: "实验类型名称", visible: true },
  { key: "sort_order", label: "排序", visible: true },
  { key: "created_at", label: "创建时间", visible: true },
  { key: "remark", label: "备注", visible: true }
]);
const roleUsers = ref([]);
const rolesStatus = ref("");
const rolesStatusState = ref("");
const loadingRoles = ref(false);
const hasRolesData = ref(false);
const roleActionUsername = ref(null);

const roleCounts = computed(() => ({
  admin: roleUsers.value.filter((item) => item.role === "admin").length,
  user: roleUsers.value.filter((item) => item.role === "user").length
}));

const rolesStatusClass = computed(() =>
  rolesStatusState.value ? `status ${rolesStatusState.value}` : "status"
);

const userFormOpen = ref(false);
const passwordFormOpen = ref(false);
const messageFormOpen = ref(false);

const editingUsername = ref(null);
const passwordUsername = ref(null);
const messageUsername = ref(null);
const messageTargetLabel = ref("");

const userAccount = ref("");
const userDisplayName = ref("");
const userClassName = ref("");
const userPassword = ref("");
const userFormStatus = ref("");
const userFormStatusState = ref("");
const savingUser = ref(false);

const userNewPassword = ref("");
const userConfirmPassword = ref("");
const passwordFormStatus = ref("");
const passwordFormStatusState = ref("");
const savingPassword = ref(false);

const adminMessageContent = ref("");
const adminMessageStatus = ref("");
const adminMessageStatusState = ref("");
const sendingMessage = ref(false);

const usersStatusClass = computed(() =>
  usersStatusState.value ? `status ${usersStatusState.value}` : "status"
);
const userFormStatusClass = computed(() =>
  userFormStatusState.value ? `status ${userFormStatusState.value}` : "status"
);
const passwordFormStatusClass = computed(() =>
  passwordFormStatusState.value ? `status ${passwordFormStatusState.value}` : "status"
);
const adminMessageStatusClass = computed(() =>
  adminMessageStatusState.value ? `status ${adminMessageStatusState.value}` : "status"
);

const messageFormTitle = computed(() =>
  messageUsername.value ? `发送私信给：${messageTargetLabel.value}` : "发送私信"
);
const userFormTitle = computed(() =>
  editingUsername.value ? `编辑用户：${editingUsername.value}` : "新增普通用户"
);
const passwordFormTitle = computed(() =>
  passwordUsername.value ? `修改用户密码：${passwordUsername.value}` : "修改用户密码"
);

const filteredUsers = computed(() => {
  const studentId = appliedStudentId.value.trim().toLocaleLowerCase();
  const studentName = appliedStudentName.value.trim().toLocaleLowerCase();
  return users.value.filter((item) => {
    const itemId = String(item.account_id || item.username || "").toLocaleLowerCase();
    const itemName = String(item.display_name || item.nickname || "").toLocaleLowerCase();
    return (
      itemId.includes(studentId) &&
      itemName.includes(studentName) &&
      (!selectedClassName.value || item.class_name === selectedClassName.value)
    );
  });
});

const emptyText = computed(() =>
  users.value.length ? "没有匹配的学生" : "暂无学生数据"
);
const experimentPageCount = computed(() =>
  Math.max(1, Math.ceil(experiments.value.length / experimentPageSize))
);
const visibleExperiments = computed(() => {
  const start = (experimentPage.value - 1) * experimentPageSize;
  return experiments.value.slice(start, start + experimentPageSize);
});
const allVisibleExperimentsSelected = computed(() =>
  visibleExperiments.value.length > 0 &&
  visibleExperiments.value.every((item) => selectedExperimentIds.value.includes(item.id))
);
const allFilteredStudentsSelected = computed(() =>
  filteredUsers.value.length > 0 &&
  filteredUsers.value.every((item) => selectedStudentUsernames.value.includes(item.username))
);
const visibleClassColumns = computed(() => classColumnOptions.value.filter((column) => column.visible));
const visibleStudentColumns = computed(() => studentColumns.value.filter((column) => column.visible));
const studentClassList = computed(() => {
  const classMap = new Map(classes.value.map((item) => [item.name, item]));
  users.value.forEach((user) => {
    const name = String(user.class_name || "").trim();
    if (name && !classMap.has(name)) classMap.set(name, { id: `student-class-${name}`, name, grade: "" });
  });
  return [...classMap.values()];
});
const filteredClasses = computed(() => {
  const query = classListSearch.value.trim().toLocaleLowerCase();
  return studentClassList.value.filter((item) => item.name.toLocaleLowerCase().includes(query));
});

function setStatus(target, message, state = "") {
  target.value = message;
  if (target === usersStatus) usersStatusState.value = state;
  else if (target === userFormStatus) userFormStatusState.value = state;
  else if (target === passwordFormStatus) passwordFormStatusState.value = state;
  else if (target === adminMessageStatus) adminMessageStatusState.value = state;
}

function registeredDate(item) {
  const date = item.registered_at ? new Date(item.registered_at) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString("zh-CN") : "—";
}

function studentCellValue(item, key) {
  if (key === "account_id") return item.account_id || item.username || "—";
  if (key === "display_name") return item.display_name || item.nickname || "—";
  if (key === "class_name") return item.class_name || "未分班";
  if (key === "grade") return classes.value.find((classItem) => classItem.name === item.class_name)?.grade || "—";
  if (key === "status") return item.status || (item.is_active === false ? "停用" : "正常");
  if (key === "registered_at") return formatClassDate(item.registered_at);
  return "—";
}

function classStudentCount(className) {
  return users.value.filter((item) => item.class_name === className).length;
}

function applyStudentFilters() {
  appliedStudentId.value = studentIdFilter.value;
  appliedStudentName.value = studentNameFilter.value;
}

function resetStudentFilters() {
  studentIdFilter.value = "";
  studentNameFilter.value = "";
  applyStudentFilters();
}

function setClassesStatus(message, state = "") {
  classesStatus.value = message;
  classesStatusState.value = state;
}

function formatClassDate(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString("zh-CN") : "—";
}

function setExperimentStatus(message, state = "") {
  experimentStatus.value = message;
  experimentStatusState.value = state;
}

function formatExperimentDate(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString("zh-CN") : "—";
}

function formatDuration(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  if (hours) return `${hours}小时 ${minutes}分`;
  if (minutes) return `${minutes}分 ${remainingSeconds}秒`;
  return `${remainingSeconds}秒`;
}

async function loadExperiments(
  keyword = experimentKeyword.value.trim(),
  experimentType = experimentTypeFilter.value
) {
  experimentLoading.value = true;
  selectedExperimentIds.value = [];
  setExperimentStatus("正在加载实验列表…", "loading");
  try {
    const params = new URLSearchParams({ keyword, experiment_type: experimentType });
    const result = await get(`/api/admin/experiments?${params}`);
    if (!Array.isArray(result.experiments)) throw new Error("实验列表格式不正确");
    experiments.value = result.experiments;
    experimentTypes.value = Array.isArray(result.experiment_types)
      ? result.experiment_types
      : [...new Set(result.experiments
        .map((item) => String(item.experiment_type || "").trim())
        .filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
    if (!keyword && !experimentType) experimentTotal.value = result.experiments.length;
    experimentPage.value = 1;
    setExperimentStatus(`共 ${experiments.value.length} 条实验记录。`, "success");
  } catch (error) {
    experiments.value = [];
    setExperimentStatus(`实验列表加载失败：${error.message}`, "error");
  } finally {
    experimentLoading.value = false;
  }
}

async function loadExperimentCount() {
  dashboardExperimentsLoading.value = true;
  dashboardExperimentsError.value = "";
  try {
    const result = await get("/api/admin/experiments");
    if (!Array.isArray(result.experiments)) throw new Error("实验列表格式不正确");
    experimentTotal.value = result.experiments.length;
    recentExperiments.value = result.experiments.slice(0, 5);
  } catch (error) {
    experimentTotal.value = null;
    recentExperiments.value = [];
    dashboardExperimentsError.value = error.message;
    dashboardStatus.value = `实验数据加载失败：${error.message}`;
  } finally {
    dashboardExperimentsLoading.value = false;
  }
}

async function loadStudentCount() {
  try {
    const result = await get("/api/admin/users");
    if (!Array.isArray(result.users)) throw new Error("用户列表格式不正确");
    studentTotal.value = result.users.filter((user) => user.role === "user").length;
  } catch (error) {
    studentTotal.value = null;
    const message = `学生人数加载失败：${error.message}`;
    dashboardStatus.value = dashboardStatus.value
      ? `${dashboardStatus.value}；${message}`
      : message;
  }
}

function resetExperimentSearch() {
  experimentKeyword.value = "";
  experimentTypeFilter.value = "";
  void loadExperiments("", "");
}

function openExperimentForm(item = null) {
  experimentEditingId.value = item?.id ?? null;
  experimentForm.value = item
    ? {
      name: item.name || "",
      experiment_type: item.experiment_type || "",
      description: item.description || ""
    }
    : { name: "", experiment_type: "", description: "" };
  experimentFormOpen.value = true;
}

function closeExperimentForm() {
  experimentFormOpen.value = false;
  experimentEditingId.value = null;
}

async function saveExperiment() {
  const payload = {
    ...experimentForm.value,
    name: experimentForm.value.name.trim()
  };
  payload.description = payload.description.trim();
  if (!payload.name || !payload.experiment_type || !payload.description) {
    setExperimentStatus("请填写实验名称、实验类型和实验简介。", "error");
    return;
  }
  experimentSaving.value = true;
  try {
    if (experimentEditingId.value) {
      await put(`/api/admin/experiments/${experimentEditingId.value}`, payload);
      setExperimentStatus("实验信息已更新。", "success");
    } else {
      await post("/api/admin/experiments", payload);
      setExperimentStatus("实验已新增。", "success");
    }
    closeExperimentForm();
    await loadExperiments();
  } catch (error) {
    setExperimentStatus(`保存失败：${error.message}`, "error");
  } finally {
    experimentSaving.value = false;
  }
}

async function toggleExperiment(item) {
  experimentActionId.value = item.id;
  try {
    const result = await put(`/api/admin/experiments/${item.id}/status`, {
      is_active: !item.is_active
    });
    experiments.value = experiments.value.map((experiment) =>
      experiment.id === item.id ? result.experiment : experiment
    );
    setExperimentStatus(result.message || "实验状态已更新。", "success");
  } catch (error) {
    setExperimentStatus(`状态更新失败：${error.message}`, "error");
  } finally {
    experimentActionId.value = null;
  }
}

async function deleteExperiment(item) {
  if (!window.confirm(`确定删除实验“${item.name}”吗？此操作不可撤销。`)) return;
  experimentActionId.value = item.id;
  try {
    await remove(`/api/admin/experiments/${item.id}`);
    await loadExperiments();
    await loadExperimentCount();
    setExperimentStatus("实验记录已删除。", "success");
  } catch (error) {
    setExperimentStatus(`删除失败：${error.message}`, "error");
  } finally {
    experimentActionId.value = null;
  }
}

function toggleExperimentSelection(experimentId) {
  selectedExperimentIds.value = selectedExperimentIds.value.includes(experimentId)
    ? selectedExperimentIds.value.filter((id) => id !== experimentId)
    : [...selectedExperimentIds.value, experimentId];
}

function toggleVisibleExperimentSelection(event) {
  const visibleIds = visibleExperiments.value.map((item) => item.id);
  selectedExperimentIds.value = event.target.checked
    ? [...new Set([...selectedExperimentIds.value, ...visibleIds])]
    : selectedExperimentIds.value.filter((id) => !visibleIds.includes(id));
}

async function batchDeleteExperiments() {
  const selectedExperiments = experiments.value.filter((item) =>
    selectedExperimentIds.value.includes(item.id)
  );
  if (!selectedExperiments.length || experimentBatchDeleting.value) return;
  const confirmed = window.confirm(
    `确定批量删除已选的 ${selectedExperiments.length} 条实验记录吗？此操作不可撤销。`
  );
  if (!confirmed) return;

  experimentBatchDeleting.value = true;
  const failures = [];
  let deletedCount = 0;
  try {
    for (const item of selectedExperiments) {
      try {
        await remove(`/api/admin/experiments/${item.id}`);
        deletedCount += 1;
      } catch (error) {
        failures.push(`${item.name}：${error.message}`);
      }
    }
    await loadExperiments();
    if (deletedCount) await loadExperimentCount();
    if (failures.length) {
      setExperimentStatus(
        `批量删除完成：成功 ${deletedCount} 条，失败 ${failures.length} 条。${failures.join("；")}`,
        "error"
      );
    } else {
      setExperimentStatus(`已批量删除 ${deletedCount} 条实验记录。`, "success");
    }
  } finally {
    experimentBatchDeleting.value = false;
  }
}

const visibleTypeColumns = computed(() => typeColumns.value.filter((column) => column.visible));

function setTypeStatus(message, state = "") {
  typeStatus.value = message;
  typeStatusState.value = state;
}

function typeCellValue(item, key) {
  if (key === "created_at") return formatExperimentDate(item.created_at);
  if (key === "sort_order") return item.sort_order ?? 0;
  return item[key] || "—";
}

function closeTypeMenus() {
  showTypeExportMenu.value = false;
  showTypeSettings.value = false;
}

function toggleTypeMenu(menu) {
  const target = menu === "export" ? showTypeExportMenu : showTypeSettings;
  const next = !target.value;
  closeTypeMenus();
  target.value = next;
}

async function loadExperimentTypes() {
  typeLoading.value = true;
  setTypeStatus("正在加载实验类型…", "loading");
  try {
    const result = await get("/api/admin/experiment-types");
    if (!Array.isArray(result.experiment_types)) throw new Error("实验类型列表格式不正确");
    typeRecords.value = result.experiment_types;
    setTypeStatus(`共 ${typeRecords.value.length} 个实验类型。`, "success");
  } catch (error) {
    typeRecords.value = [];
    setTypeStatus(`实验类型加载失败：${error.message}`, "error");
  } finally {
    typeLoading.value = false;
  }
}

function openTypeForm(item = null, copyFrom = null) {
  closeTypeMenus();
  typeEditingId.value = item?.id ?? null;
  typeForm.value = item
    ? {
      name: item.name || "",
      sort_order: item.sort_order ?? 0,
      remark: item.remark || ""
    }
    : {
      name: "",
      sort_order: copyFrom ? Number(copyFrom.sort_order || 0) + 1 : typeRecords.value.length + 1,
      remark: ""
    };
  typeFormOpen.value = true;
}

function closeTypeForm() {
  typeFormOpen.value = false;
  typeEditingId.value = null;
}

async function saveType() {
  const payload = {
    name: typeForm.value.name.trim(),
    sort_order: Number(typeForm.value.sort_order) || 0,
    remark: typeForm.value.remark.trim()
  };
  if (!payload.name) {
    setTypeStatus("请填写实验类型名称。", "error");
    return;
  }
  typeSaving.value = true;
  try {
    if (typeEditingId.value) {
      await put(`/api/admin/experiment-types/${typeEditingId.value}`, payload);
      setTypeStatus("实验类型已更新。", "success");
    } else {
      await post("/api/admin/experiment-types", payload);
      setTypeStatus("实验类型已新增。", "success");
    }
    closeTypeForm();
    await loadExperimentTypes();
  } catch (error) {
    setTypeStatus(`保存失败：${error.message}`, "error");
  } finally {
    typeSaving.value = false;
  }
}

async function deleteType(item) {
  if (!window.confirm(`确定删除实验类型“${item.name}”吗？此操作不可撤销。`)) return;
  typeActionId.value = item.id;
  try {
    await remove(`/api/admin/experiment-types/${item.id}`);
    await loadExperimentTypes();
    setTypeStatus("实验类型已删除。", "success");
  } catch (error) {
    setTypeStatus(`删除失败：${error.message}`, "error");
  } finally {
    typeActionId.value = null;
  }
}

function downloadTypeTemplate() {
  closeTypeMenus();
  downloadCsv("实验类型导入模板.csv", [["实验类型名称", "排序", "备注"]]);
}

function exportTypes() {
  closeTypeMenus();
  const columns = ["实验类型名称", "排序", "创建时间", "备注"];
  const rows = typeRecords.value.map((item) => [
    item.name,
    item.sort_order ?? 0,
    formatExperimentDate(item.created_at),
    item.remark || ""
  ]);
  downloadCsv("实验类型.csv", [columns, ...rows]);
}

async function importTypes(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  importingTypes.value = true;
  let imported = 0;
  const failures = [];
  try {
    const rows = await readTableRows(file);
    if (rows.length < 2) throw new Error("模板中没有可导入的实验类型");
    const headers = rows[0].map((header) => String(header ?? "").trim());
    const nameIndex = findHeaderIndex(headers, ["实验类型名称", "类型名称", "实验类型", "名称", "name"]);
    if (nameIndex < 0) {
      throw new Error(`未识别到表头「实验类型名称」，实际读到：${headers.filter(Boolean).join(" / ") || "空"}`);
    }
    const sortIndex = findHeaderIndex(headers, ["排序", "顺序", "sortorder", "sort"]);
    const remarkIndex = findHeaderIndex(headers, ["备注", "说明", "描述", "remark"]);

    for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
      const name = String(rows[rowIndex][nameIndex] ?? "").trim();
      const sortOrder = sortIndex >= 0 ? Number(String(rows[rowIndex][sortIndex] ?? "").trim() || 0) : 0;
      const remark = remarkIndex >= 0 ? String(rows[rowIndex][remarkIndex] ?? "").trim() : "";
      if (!name) continue;
      try {
        await post("/api/admin/experiment-types", {
          name,
          sort_order: Number.isFinite(sortOrder) ? sortOrder : 0,
          remark
        });
        imported += 1;
      } catch (error) {
        failures.push(`第 ${rowIndex + 1} 行：${error.message}`);
      }
    }

    await loadExperimentTypes();
    const summary = `导入完成：成功 ${imported} 条，失败 ${failures.length} 条。`;
    setTypeStatus(
      `${summary}${failures.length ? ` ${failures.slice(0, 3).join("；")}` : ""}`,
      failures.length ? "error" : "success"
    );
  } catch (error) {
    setTypeStatus(`导入失败：${error.message}`, "error");
  } finally {
    importingTypes.value = false;
    event.target.value = "";
  }
}

function selectSection(section) {
  adminSection.value = section;
  dashboardStatus.value = "";
  closeTypeMenus();
  if (Object.hasOwn(adminSectionMeta, section)) {
    recentSections.value = [
      section,
      ...recentSections.value.filter((recentSection) => recentSection !== section)
    ].slice(0, recentSectionLimit);
    localStorage.setItem(recentSectionStorageKey, JSON.stringify(recentSections.value));
  }
  if (section === "users") {
    void loadUsers();
    void loadClasses();
  }
  if (section === "classes") void loadClasses();
  if (section === "roles") void loadRoles();
  if (section === "experiments") void loadExperiments();
  if (section === "experimentTypes") void loadExperimentTypes();
}

function refreshDashboard() {
  lastRefreshed.value = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  if (adminSection.value === "users") {
    void loadUsers();
    void loadClasses();
  }
  else if (adminSection.value === "classes") void loadClasses();
  else if (adminSection.value === "roles") void loadRoles();
  else if (adminSection.value === "experiments") void loadExperiments();
  else if (adminSection.value === "experimentTypes") void loadExperimentTypes();
  else {
    dashboardStatus.value = "";
    void loadExperimentCount();
    void loadStudentCount();
  }
}

function closeForms() {
  userFormOpen.value = false;
  passwordFormOpen.value = false;
  messageFormOpen.value = false;
  editingUsername.value = null;
  passwordUsername.value = null;
  messageUsername.value = null;
  messageTargetLabel.value = "";
}

function resetUserForm() {
  userAccount.value = "";
  userDisplayName.value = "";
  userClassName.value = "";
  userPassword.value = "";
}

async function loadUsers() {
  setStatus(usersStatus, "正在加载用户…", "loading");
  try {
    const result = await get("/api/admin/users");
    if (!Array.isArray(result.users)) throw new Error("用户列表格式不正确");
    users.value = result.users.filter((item) => item.role !== "admin");
    const availableUsernames = new Set(users.value.map((item) => item.username));
    selectedStudentUsernames.value = selectedStudentUsernames.value.filter((username) =>
      availableUsernames.has(username)
    );
    studentTotal.value = result.users.filter((item) => item.role === "user").length;
    setStatus(usersStatus, `加载成功，共 ${users.value.length} 位普通用户。`, "success");
  } catch (error) {
    users.value = [];
    studentTotal.value = null;
    setStatus(usersStatus, `用户列表加载失败：${error.message}`, "error");
  }
}

async function loadClasses() {
  classesLoading.value = true;
  setClassesStatus("正在加载班级列表…", "loading");
  const params = new URLSearchParams({
    keyword: classNameFilter.value.trim(),
    grade: classGradeFilter.value.trim()
  });
  try {
    // 人数以学生列表为准实时统计，后端未重启（仍返回旧的手工人数字段）时也能保持一致
    const [result, userResult] = await Promise.all([
      get(`/api/admin/classes?${params}`),
      get("/api/admin/users").catch(() => null)
    ]);
    if (!Array.isArray(result.classes)) throw new Error("班级列表格式不正确");
    const hasLiveCounts = Array.isArray(userResult?.users);
    const counts = new Map();
    if (hasLiveCounts) {
      userResult.users
        .filter((item) => item.role !== "admin")
        .forEach((item) => {
          const name = String(item.class_name || "").trim();
          if (name) counts.set(name, (counts.get(name) || 0) + 1);
        });
    }
    classes.value = result.classes.map((item) =>
      hasLiveCounts
        ? { ...item, student_count: counts.get(String(item.name || "").trim()) ?? 0 }
        : item
    );
    setClassesStatus(`共 ${classes.value.length} 个班级，人数按学生列表自动统计。`, "success");
  } catch (error) {
    classes.value = [];
    setClassesStatus(`班级列表加载失败：${error.message}`, "error");
  } finally {
    classesLoading.value = false;
  }
}

function resetClassFilters() {
  classNameFilter.value = "";
  classGradeFilter.value = "";
  void loadClasses();
}

function openClassForm(item = null) {
  classEditingId.value = item?.id ?? null;
  classForm.value = item
    ? {
        name: item.name || "",
        grade: item.grade || "",
        student_count: item.student_count || 0,
        sort_order: item.sort_order || 0,
        remark: item.remark || ""
      }
    : { name: "", grade: "", student_count: 0, sort_order: 0, remark: "" };
  classFormOpen.value = true;
}

function closeClassForm() {
  classFormOpen.value = false;
  classEditingId.value = null;
}

async function saveClass() {
  // 人数是派生数据，不随表单提交，由后端按学生表统计
  const payload = {
    name: classForm.value.name.trim(),
    grade: classForm.value.grade.trim(),
    sort_order: Number(classForm.value.sort_order) || 0,
    remark: classForm.value.remark.trim()
  };
  if (!payload.name || !payload.grade) {
    setClassesStatus("请填写班级名称和年级。", "error");
    return;
  }
  classSaving.value = true;
  try {
    if (classEditingId.value) {
      const result = await put(`/api/admin/classes/${classEditingId.value}`, payload);
      setClassesStatus(result?.message || "班级信息已更新。", "success");
    } else {
      const result = await post("/api/admin/classes", payload);
      setClassesStatus(result?.message || "班级已新增。", "success");
    }
    closeClassForm();
    // 改名会联动更新学生所属班级，同步刷新学生缓存，避免左侧班级列表残留旧班级名
    void loadUsers();
    await loadClasses();
  } catch (error) {
    setClassesStatus(`保存失败：${error.message}`, "error");
  } finally {
    classSaving.value = false;
  }
}

async function deleteClass(item) {
  if (!window.confirm(`确定删除班级“${item.name}”吗？此操作不可撤销。`)) return;
  classActionId.value = item.id;
  try {
    await remove(`/api/admin/classes/${item.id}`);
    await loadClasses();
    setClassesStatus("班级已删除。", "success");
  } catch (error) {
    setClassesStatus(`删除失败：${error.message}`, "error");
  } finally {
    classActionId.value = null;
  }
}

async function loadRoles() {
  loadingRoles.value = true;
  rolesStatus.value = "正在加载角色信息…";
  rolesStatusState.value = "loading";
  try {
    const result = await get("/api/admin/users");
    if (!Array.isArray(result.users)) throw new Error("用户列表格式不正确");
    roleUsers.value = result.users;
    hasRolesData.value = true;
    rolesStatus.value = `角色信息已更新，共 ${result.users.length} 个账号。`;
    rolesStatusState.value = "success";
  } catch (error) {
    roleUsers.value = [];
    hasRolesData.value = false;
    rolesStatus.value = `角色信息加载失败：${error.message}`;
    rolesStatusState.value = "error";
  } finally {
    loadingRoles.value = false;
  }
}

async function promoteUserToAdmin(user) {
  if (roleActionUsername.value) return;
  if (!window.confirm(`确定将“${user.display_name || user.username}”提升为管理员吗？`)) return;
  roleActionUsername.value = user.username;
  try {
    const result = await put(`/api/admin/users/${encodeURIComponent(user.username)}/role`, {});
    await loadRoles();
    rolesStatus.value = result.message || "用户已提升为管理员。";
    rolesStatusState.value = "success";
  } catch (error) {
    rolesStatus.value = `提升管理员失败：${error.message}`;
    rolesStatusState.value = "error";
  } finally {
    roleActionUsername.value = null;
  }
}

async function toggleAdminStatus(user) {
  if (roleActionUsername.value) return;
  const isActive = !user.is_active;
  const action = isActive ? "启用" : "停用";
  if (!window.confirm(`确定${action}管理员账号“${user.display_name || user.username}”吗？`)) return;
  roleActionUsername.value = user.username;
  try {
    const result = await put(`/api/admin/users/${encodeURIComponent(user.username)}/status`, {
      is_active: isActive
    });
    await loadRoles();
    rolesStatus.value = result.message || `管理员账号已${action}。`;
    rolesStatusState.value = "success";
  } catch (error) {
    rolesStatus.value = `${action}管理员失败：${error.message}`;
    rolesStatusState.value = "error";
  } finally {
    roleActionUsername.value = null;
  }
}

function openCreateForm() {
  closeForms();
  editingUsername.value = null;
  resetUserForm();
  userClassName.value = selectedClassName.value;
  setStatus(userFormStatus, "");
  userFormOpen.value = true;
}

function openEditForm(item) {
  closeForms();
  editingUsername.value = item.username;
  userAccount.value = item.account_id || item.student_id || item.username;
  userDisplayName.value = item.display_name || item.nickname || "";
  userClassName.value = item.class_name || "";
  userPassword.value = "";
  setStatus(userFormStatus, "");
  userFormOpen.value = true;
}

async function onAction(action, item) {
  if (action === "edit") {
    openStudentBatchEdit(item);
    return;
  }
  if (action === "password") {
    closeForms();
    passwordUsername.value = item.username;
    userNewPassword.value = "";
    userConfirmPassword.value = "";
    setStatus(passwordFormStatus, "");
    passwordFormOpen.value = true;
    return;
  }
  if (action === "message") {
    closeForms();
    messageUsername.value = item.username;
    messageTargetLabel.value = item.display_name || item.username;
    adminMessageContent.value = "";
    setStatus(adminMessageStatus, "");
    messageFormOpen.value = true;
    await nextTick();
    document.getElementById("messagePanel")?.scrollIntoView({ behavior: "smooth", block: "center" });
    document.getElementById("adminMessageContent")?.focus({ preventScroll: true });
    return;
  }
  if (action === "delete" && window.confirm(`确定删除普通用户“${item.username}”吗？此操作不可撤销。`)) {
    setStatus(usersStatus, `正在删除用户 ${item.username}…`, "loading");
    try {
      await remove(`/api/admin/users/${encodeURIComponent(item.username)}`);
      setStatus(usersStatus, `用户 ${item.username} 已删除。`, "success");
      await loadUsers();
    } catch (error) {
      setStatus(usersStatus, `删除失败：${error.message}`, "error");
    }
  }
}

function toggleStudentSelection(username) {
  selectedStudentUsernames.value = selectedStudentUsernames.value.includes(username)
    ? selectedStudentUsernames.value.filter((selectedUsername) => selectedUsername !== username)
    : [...selectedStudentUsernames.value, username];
}

function toggleFilteredStudentSelection(event) {
  const filteredUsernames = filteredUsers.value.map((item) => item.username);
  selectedStudentUsernames.value = event.target.checked
    ? [...new Set([...selectedStudentUsernames.value, ...filteredUsernames])]
    : selectedStudentUsernames.value.filter((username) => !filteredUsernames.includes(username));
}

async function batchDeleteStudents() {
  const selectedStudents = users.value.filter((item) =>
    selectedStudentUsernames.value.includes(item.username)
  );
  if (!selectedStudents.length || studentBatchDeleting.value) return;
  if (!window.confirm(`确定批量删除已选的 ${selectedStudents.length} 位学生吗？此操作不可撤销。`)) return;

  studentBatchDeleting.value = true;
  const failures = [];
  let deletedCount = 0;
  try {
    for (const student of selectedStudents) {
      try {
        await remove(`/api/admin/users/${encodeURIComponent(student.username)}`);
        deletedCount += 1;
      } catch (error) {
        failures.push(`${student.display_name || student.username}：${error.message}`);
      }
    }
    await loadUsers();
    if (deletedCount) await loadClasses();
    setStatus(
      usersStatus,
      failures.length
        ? `批量删除完成：成功 ${deletedCount} 位，失败 ${failures.length} 位。${failures.slice(0, 3).join("；")}`
        : `已批量删除 ${deletedCount} 位学生。`,
      failures.length ? "error" : "success"
    );
  } finally {
    studentBatchDeleting.value = false;
  }
}

function openStudentBatchEdit(student = null) {
  const usernames = student ? [student.username] : [...selectedStudentUsernames.value];
  if (!usernames.length || studentBatchEditing.value) return;
  studentBatchEditUsernames.value = usernames;
  studentBatchChangeClass.value = false;
  studentBatchResetPassword.value = false;
  studentBatchClassName.value = "";
  studentBatchGrade.value = "";
  studentBatchNewPassword.value = "";
  studentBatchEditError.value = "";
  studentBatchEditOpen.value = true;
}

function closeStudentBatchEdit(force = false) {
  if (studentBatchEditing.value && !force) return;
  studentBatchEditOpen.value = false;
  studentBatchEditUsernames.value = [];
  studentBatchNewPassword.value = "";
}

async function saveStudentBatchEdit() {
  const selectedStudents = users.value.filter((item) =>
    studentBatchEditUsernames.value.includes(item.username)
  );
  if (!selectedStudents.length || studentBatchEditing.value) return;

  const changeClass = studentBatchChangeClass.value;
  const resetPassword = studentBatchResetPassword.value;
  const className = studentBatchClassName.value.trim();
  const grade = studentBatchGrade.value.trim();
  const newPassword = studentBatchNewPassword.value;
  if (!changeClass && !grade && !resetPassword) {
    studentBatchEditError.value = "请至少选择一项批量编辑操作。";
    return;
  }
  if (changeClass && grade && !className) {
    studentBatchEditError.value = "设置年级时请填写目标班级，或取消勾选调整所属班级。";
    return;
  }
  if (resetPassword && newPassword.length < 8) {
    studentBatchEditError.value = "批量重置密码至少需要 8 位。";
    return;
  }
  if (resetPassword && !window.confirm(`确定将已选 ${selectedStudents.length} 位学生的密码统一重置吗？`)) return;

  studentBatchEditing.value = true;
  studentBatchEditError.value = "";
  const failures = [];
  let updatedCount = 0;
  let updatedClassCount = 0;
  let resetPasswordCount = 0;
  try {
    const gradeClassNames = changeClass
      ? (className && grade ? [className] : [])
      : [...new Set(selectedStudents.map((student) => String(student.class_name || "").trim()).filter(Boolean))];
    if (changeClass && className) {
      const { failures: classCreationFailures } = await ensureClasses(
        new Map([[className, grade || "未设置"]])
      );
      if (classCreationFailures.length) {
        studentBatchEditError.value = `班级创建失败：${classCreationFailures.join("；")}`;
        return;
      }
    }

    if (changeClass) {
      for (const student of selectedStudents) {
        try {
          await patch(`/api/admin/users/${encodeURIComponent(student.username)}`, {
            class_name: className
          });
          updatedCount += 1;
        } catch (error) {
          failures.push(`${student.display_name || student.username}：${error.message}`);
        }
      }
    }

    if (resetPassword) {
      for (const student of selectedStudents) {
        try {
          await put(`/api/admin/users/${encodeURIComponent(student.username)}/password`, {
            new_password: newPassword
          });
          resetPasswordCount += 1;
        } catch (error) {
          failures.push(`${student.display_name || student.username} 密码：${error.message}`);
        }
      }
    }

    if (grade && gradeClassNames.length) {
      try {
        const result = await get("/api/admin/classes");
        if (!Array.isArray(result.classes)) throw new Error("班级列表格式不正确");
        for (const name of gradeClassNames) {
          const classItem = result.classes.find((item) => item.name === name);
          if (!classItem) {
            failures.push(`${name}：未找到班级，无法更新年级`);
            continue;
          }
          try {
            await put(`/api/admin/classes/${classItem.id}`, { ...classItem, grade });
            updatedClassCount += 1;
          } catch (error) {
            failures.push(`${name}：${error.message}`);
          }
        }
      } catch (error) {
        failures.push(`读取班级列表失败：${error.message}`);
      }
    } else if (grade) {
      failures.push("所选学生均未分班，无法调整年级");
    }

    await loadUsers();
    await loadClasses();
    closeStudentBatchEdit(true);
    setStatus(
      usersStatus,
      failures.length
        ? `批量编辑完成：更新 ${updatedCount} 位学生班级、${updatedClassCount} 个班级年级、重置 ${resetPasswordCount} 个密码，失败 ${failures.length} 项。${failures.slice(0, 3).join("；")}`
        : `批量编辑完成：更新 ${updatedCount} 位学生班级、${updatedClassCount} 个班级年级、重置 ${resetPasswordCount} 个密码。`,
      failures.length ? "error" : "success"
    );
  } finally {
    studentBatchEditing.value = false;
  }
}

async function submitUserForm() {
  const account = userAccount.value.trim();
  const name = userDisplayName.value.trim();
  const className = String(userClassName.value ?? "").trim();
  savingUser.value = true;
  setStatus(userFormStatus, editingUsername.value ? "正在保存用户信息…" : "正在创建用户…", "loading");
  try {
    let successMessage = editingUsername.value ? "用户信息已更新。" : "用户创建成功。";
    if (editingUsername.value) {
      await patch(`/api/admin/users/${encodeURIComponent(editingUsername.value)}`, {
        display_name: name,
        class_name: className
      });
    } else {
      await post("/api/admin/users", {
        username: account,
        account_id: account,
        display_name: name,
        password: userPassword.value,
        class_name: className,
        role: "user"
      });
    }
    // 手动填写的新班级名自动补建；把学生改到另一个新班级时同样生效
    const { created: createdClasses, failures: classFailures } = await ensureClasses(
      className ? new Map([[className, ""]]) : new Map()
    );
    if (createdClasses.length) successMessage += ` 已自动新建班级：${createdClasses.join("、")}。`;
    if (classFailures.length) successMessage += ` 班级创建失败：${classFailures.join("；")}`;
    await loadUsers();
    await loadClasses();
    if (usersStatusState.value === "success" || createdClasses.length || classFailures.length) {
      setStatus(usersStatus, successMessage, classFailures.length ? "error" : "success");
    }
    resetUserForm();
    closeForms();
  } catch (error) {
    setStatus(userFormStatus, `操作失败：${error.message}`, "error");
  } finally {
    savingUser.value = false;
  }
}

/* ---------- 表格文件解析：CSV（UTF-8 / GBK / UTF-16 / TSV）与 Excel .xlsx ---------- */
function decodeTableText(buffer) {
  const bytes = new Uint8Array(buffer);
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder("utf-16le").decode(bytes);
  if (bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder("utf-16be").decode(bytes);
  const utf8 = new TextDecoder("utf-8").decode(bytes);
  if (utf8.includes("\uFFFD")) {
    try {
      const gbk = new TextDecoder("gb18030").decode(bytes);
      if (!gbk.includes("\uFFFD")) return gbk;
    } catch {
      /* 浏览器不支持 gb18030 时保留 UTF-8 结果 */
    }
  }
  return utf8;
}

function detectDelimiter(text) {
  const firstLine = text.split(/\r?\n/)[0] || "";
  let best = ",";
  let bestCount = 0;
  for (const delimiter of [",", "\t", ";", "|"]) {
    const count = firstLine.split(delimiter).length - 1;
    if (count > bestCount) {
      best = delimiter;
      bestCount = count;
    }
  }
  return best;
}

function parseCsv(text, delimiter = ",") {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;
  const source = text.replace(/^\uFEFF/, "");
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (quoted) {
      if (character === '"' && source[index + 1] === '"') {
        value += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        value += character;
      }
    } else if (character === '"' && value === "") {
      quoted = true;
    } else if (character === delimiter) {
      row.push(value);
      value = "";
    } else if (character === "\n") {
      row.push(value.replace(/\r$/, ""));
      if (row.some((cell) => cell.trim())) rows.push(row);
      row = [];
      value = "";
    } else {
      value += character;
    }
  }
  row.push(value.replace(/\r$/, ""));
  if (row.some((cell) => cell.trim())) rows.push(row);
  return rows;
}

function columnIndexFromRef(ref) {
  const letters = String(ref || "").match(/^[A-Za-z]+/)?.[0];
  if (!letters) return -1;
  let index = 0;
  for (const char of letters.toUpperCase()) index = index * 26 + char.charCodeAt(0) - 64;
  return index - 1;
}

function normalizeNumberText(text) {
  if (!/[eE]/.test(text)) return text;
  const number = Number(text);
  return Number.isFinite(number) && Number.isInteger(number) ? String(number) : text;
}

// 学生导入表格的必需列（含常见别名），解析与选表都用这一份定义
const STUDENT_HEADER_GROUPS = [
  { label: "学号", aliases: ["学号", "学生学号", "账号", "用户账号", "account", "accountid", "studentid"] },
  { label: "姓名", aliases: ["姓名", "学生姓名", "名称", "name", "displayname"] },
  { label: "所属班级", aliases: ["所属班级", "班级", "班级名称", "class", "classname"] },
  { label: "初始密码", aliases: ["初始密码", "登录密码", "密码", "password"] }
];

function parseXlsxSheetRows(files, sheetPath, sharedStrings, parser) {
  const sheet = parser.parseFromString(strFromU8(files[sheetPath]), "application/xml");
  if (sheet.getElementsByTagName("parsererror").length) throw new Error("Excel 工作表内容无法解析");
  const rows = [];
  for (const rowNode of Array.from(sheet.getElementsByTagName("row"))) {
    const row = [];
    for (const cell of Array.from(rowNode.getElementsByTagName("c"))) {
      let index = columnIndexFromRef(cell.getAttribute("r"));
      if (index < 0) index = row.length;
      const type = cell.getAttribute("t") || "";
      let value = "";
      if (type === "inlineStr") {
        for (const node of Array.from(cell.getElementsByTagName("t"))) value += node.textContent || "";
      } else {
        const raw = cell.getElementsByTagName("v")[0]?.textContent || "";
        value = type === "s" ? sharedStrings[Number(raw)] ?? "" : normalizeNumberText(raw);
      }
      row[index] = value;
    }
    for (let index = 0; index < row.length; index += 1) if (row[index] === undefined) row[index] = "";
    if (row.some((cell) => String(cell).trim())) rows.push(row);
  }
  return rows;
}

function parseXlsx(buffer) {
  let files;
  try {
    files = unzipSync(new Uint8Array(buffer));
  } catch {
    throw new Error("Excel 文件无法解析，请确认文件未损坏且未加密");
  }
  const entries = Object.keys(files);
  const sheetPaths = entries
    .filter((name) => /^xl\/worksheets\/[^/]+\.xml$/i.test(name))
    .sort((left, right) => left.localeCompare(right, "en", { numeric: true }));
  if (!sheetPaths.length) throw new Error("Excel 文件中没有找到工作表");

  const parser = new DOMParser();
  const sharedStrings = [];
  const sharedPath = entries.find((name) => /^xl\/sharedStrings\.xml$/i.test(name));
  if (sharedPath) {
    const doc = parser.parseFromString(strFromU8(files[sharedPath]), "application/xml");
    for (const item of Array.from(doc.getElementsByTagName("si"))) {
      let text = "";
      for (const node of Array.from(item.getElementsByTagName("t"))) {
        if (/rPh/i.test(node.parentNode?.nodeName || "")) continue;
        text += node.textContent || "";
      }
      sharedStrings.push(text);
    }
  }

  // 工作簿里可能有多张表（如「填写说明」在第一张）：挑表头命中最多的一张，而不是死读 sheet1
  let bestRows = null;
  let bestScore = -1;
  for (const sheetPath of sheetPaths) {
    const rows = parseXlsxSheetRows(files, sheetPath, sharedStrings, parser);
    let score = 0;
    for (let rowIndex = 0; rowIndex < Math.min(rows.length, 5); rowIndex += 1) {
      const headerCells = rows[rowIndex].map((cell) => String(cell ?? "").trim());
      const hits = STUDENT_HEADER_GROUPS.filter((group) => findHeaderIndex(headerCells, group.aliases) >= 0).length;
      if (hits > score) score = hits;
    }
    if (score > bestScore) {
      bestScore = score;
      bestRows = rows;
    }
    if (score === STUDENT_HEADER_GROUPS.length) break;
  }
  return bestRows ?? [];
}

async function readTableRows(file, providedBuffer) {
  const buffer = providedBuffer ?? (await file.arrayBuffer());
  const bytes = new Uint8Array(buffer);
  const isZip = bytes[0] === 0x50 && bytes[1] === 0x4b;
  if (isZip || /\.xlsx$/i.test(file.name)) return parseXlsx(buffer);
  if (/\.xls$/i.test(file.name)) throw new Error("旧版 .xls 请先用 Excel/WPS 另存为 .xlsx 或 CSV UTF-8");
  const text = decodeTableText(buffer);
  return parseCsv(text, detectDelimiter(text));
}

function formatFileSize(size) {
  if (!Number.isFinite(size)) return "未知大小";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function formatFileTime(timestamp) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "未知";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "未知";
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

// 文件指纹（SHA-256 前 4 字节）：同名文件内容不同时，指纹一定不同，用来确认浏览器读的是哪一份文件
async function fileFingerprint(buffer) {
  try {
    if (!window.crypto?.subtle) return "";
    const digest = await window.crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(digest))
      .slice(0, 4)
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase();
  } catch {
    return "";
  }
}

function normalizeHeader(value) {
  return String(value ?? "")
    .replace(/[（(【\[][^）)】\]]*[）)】\]]/g, "")
    .replace(/[\s\u3000\u00A0\uFEFF\u200B]/g, "")
    .toLowerCase();
}

function findHeaderIndex(headers, aliases) {
  const normalized = headers.map(normalizeHeader);
  for (const alias of aliases) {
    const index = normalized.indexOf(normalizeHeader(alias));
    if (index >= 0) return index;
  }
  return -1;
}

// 允许 Excel 表格在表头上方加标题行：在前几行里找能完整匹配所有字段的那一行
function locateHeaders(rows, groups, maxRows = 5) {
  let fallback = { rowIndex: 0, indexes: groups.map(() => -1), headers: [] };
  for (let rowIndex = 0; rowIndex < Math.min(rows.length, maxRows); rowIndex += 1) {
    const headers = rows[rowIndex].map((header) => String(header ?? "").trim());
    const indexes = groups.map((group) => findHeaderIndex(headers, group.aliases));
    if (rowIndex === 0) fallback = { rowIndex, indexes, headers };
    if (indexes.every((index) => index >= 0)) return { rowIndex, indexes, headers };
  }
  return fallback;
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(filename, rows) {
  const content = `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadImportTemplate() {
  downloadCsv("学生导入模板.csv", [["学号", "姓名", "所属班级", "初始密码"]]);
}

function exportStudents() {
  const columns = ["学号", "姓名", "所属班级", "年级", "状态", "创建时间"];
  const rows = filteredUsers.value.map((item) => [
    studentCellValue(item, "account_id"),
    studentCellValue(item, "display_name"),
    studentCellValue(item, "class_name"),
    studentCellValue(item, "grade"),
    studentCellValue(item, "status"),
    studentCellValue(item, "registered_at")
  ]);
  downloadCsv("学生信息.csv", [columns, ...rows]);
}

// 自动补建学生所属班级：classes 表中不存在的班级自动创建，供「导入」与「手动新增/编辑学生」共用
// classEntries 为 Map<班级名, 年级>，年级为空时使用后端允许的默认值「未设置」
async function ensureClasses(classEntries) {
  const created = [];
  const failures = [];
  if (!classEntries?.size) return { created, failures };
  let classRows = [];
  try {
    const result = await get("/api/admin/classes");
    if (Array.isArray(result.classes)) classRows = result.classes;
  } catch {
    // 读取班级列表失败时仍尝试创建，由后端兜底
  }
  const known = new Set(classRows.map((item) => String(item.name ?? "").trim()));
  let nextSort = classRows.reduce((max, item) => Math.max(max, Number(item.sort_order) || 0), 0);
  for (const [rawName, grade] of classEntries) {
    const name = String(rawName ?? "").trim();
    if (!name || known.has(name)) continue;
    nextSort += 1;
    try {
      await post("/api/admin/classes", {
        name,
        grade: String(grade ?? "").trim() || "未设置",
        sort_order: nextSort,
        remark: "创建学生时自动补建"
      });
      known.add(name);
      created.push(name);
    } catch (error) {
      failures.push(`${name}：${error.message}`);
    }
  }
  return { created, failures };
}

async function importStudents(event) {
  const file = event.target.files?.[0];
  if (file) await runImportFile(file);
  event.target.value = "";
}

// 拖拽导入：从资源管理器直接拖文件进来，避免文件对话框里选到云文档或其他同名副本
const importDragActive = ref(false);

function onImportDragOver() {
  if (!importingStudents.value) importDragActive.value = true;
}

function onImportDragLeave(event) {
  const next = event.relatedTarget;
  if (next && event.currentTarget?.contains(next)) return;
  importDragActive.value = false;
}

async function onImportDrop(event) {
  importDragActive.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (!file || importingStudents.value) return;
  if (!/\.(xlsx|csv|xls)$/i.test(file.name)) {
    setStatus(usersStatus, `不支持的拖入文件「${file.name}」，请拖入 .xlsx 或 .csv 文件。`, "error");
    return;
  }
  await runImportFile(file);
}

async function runImportFile(file) {
  importingStudents.value = true;
  let imported = 0;
  let skipped = 0;
  let fingerprint = "";
  const failures = [];
  const readAccounts = [];
  try {
    const buffer = await file.arrayBuffer();
    fingerprint = await fileFingerprint(buffer);
    const rows = await readTableRows(file, buffer);
    if (rows.length < 2) throw new Error("模板中没有可导入的学生记录");
    const headerGroups = STUDENT_HEADER_GROUPS;
    const { rowIndex: headerRow, indexes, headers } = locateHeaders(rows, headerGroups);
    const missing = headerGroups.filter((group, position) => indexes[position] < 0).map((group) => group.label);
    if (missing.length) {
      const actual = headers.filter(Boolean).join(" / ") || "空";
      throw new Error(`未识别到表头「${missing.join("、")}」，实际读到：${actual}`);
    }
    // 「年级」为可选列：模板里没有时，自动补建的班级使用默认年级
    const gradeIndex = findHeaderIndex(headers, ["年级", "入学年级", "grade"]);

    // 先取回系统里已有的学号：重复的行直接跳过，不再算作失败
    const existing = new Set();
    try {
      const result = await get("/api/admin/users");
      if (Array.isArray(result.users)) {
        result.users.forEach((item) => existing.add(String(item.username ?? "").trim()));
      }
    } catch {
      // 读取失败时仍继续，由后端 409 兜底判重
    }

    // 先扫描文件里的班级并在导入学生之前建好，保证文件里的「年级」列优先生效
    const importedClasses = new Map();
    for (let rowIndex = headerRow + 1; rowIndex < rows.length; rowIndex += 1) {
      const values = indexes.map((index) => String(rows[rowIndex][index] ?? "").trim());
      const [account, name, className, password] = values;
      if (!values.some(Boolean)) continue;
      if (!/^\d+$/.test(account) || !name || password.length < 8) continue;
      const grade = gradeIndex >= 0 ? String(rows[rowIndex][gradeIndex] ?? "").trim() : "";
      if (className && !importedClasses.has(className)) importedClasses.set(className, grade);
    }
    const { created: createdClasses, failures: classFailures } = await ensureClasses(importedClasses);

    for (let rowIndex = headerRow + 1; rowIndex < rows.length; rowIndex += 1) {
      const values = indexes.map((index) => String(rows[rowIndex][index] ?? "").trim());
      const [account, name, className, password] = values;
      if (!values.some(Boolean)) continue;
      readAccounts.push(account || "（空）");
      if (!/^\d+$/.test(account) || !name || password.length < 8) {
        failures.push(`第 ${rowIndex + 1} 行（学号 ${account || "空"}）：学号须为数字、姓名不能为空、密码至少 8 位`);
        continue;
      }
      if (existing.has(account)) {
        skipped += 1;
        continue;
      }
      try {
        await post("/api/admin/users", {
          username: account,
          account_id: account,
          display_name: name,
          class_name: className,
          password,
          role: "user"
        });
        existing.add(account);
        imported += 1;
      } catch (error) {
        // 后端已存在（并发或缓存不一致）同样按跳过处理，避免整轮显示失败
        if (error?.status === 409 || /该账号已存在/.test(error?.message || "")) {
          skipped += 1;
          continue;
        }
        failures.push(`第 ${rowIndex + 1} 行（学号 ${account}）：${error.message}`);
      }
    }

    await loadUsers();
    await loadClasses();
    const preview = readAccounts.slice(0, 12).join("、");
    const more = readAccounts.length > 12 ? ` 等 ${readAccounts.length} 个` : "";
    const summary = `导入完成：成功 ${imported} 条，跳过已存在 ${skipped} 条，失败 ${failures.length} 条。`;
    const fileInfo = `本次读取「${file.name}」（${formatFileSize(file.size)}，修改于 ${formatFileTime(file.lastModified)}${fingerprint ? `，指纹 ${fingerprint}` : ""}）中的学号：${preview || "无"}${more}。`;
    const detail = failures.length ? ` ${failures.slice(0, 3).join("；")}` : "";
    const classInfo = createdClasses.length
      ? ` 自动新建班级 ${createdClasses.length} 个：${createdClasses.join("、")}。`
      : "";
    const classError = classFailures.length ? ` 班级创建失败：${classFailures.slice(0, 2).join("；")}` : "";
    const allSkipped = !imported && !failures.length && skipped > 0 && skipped === readAccounts.length;
    const skipHint = allSkipped ? " 提示：这个文件里的账号全部已存在，注意是否选到了旧副本或云文档里的旧版文件。" : "";
    const state = failures.length || classFailures.length ? "error" : imported || createdClasses.length ? "success" : "loading";
    setStatus(usersStatus, `${summary}${fileInfo}${classInfo}${detail}${classError}${skipHint}`, state);
  } catch (error) {
    setStatus(usersStatus, `导入失败：${error.message}（文件：${file.name}）`, "error");
  } finally {
    importingStudents.value = false;
  }
}

async function submitPasswordForm() {
  if (userNewPassword.value !== userConfirmPassword.value) {
    setStatus(passwordFormStatus, "两次输入的新密码不一致。", "error");
    return;
  }
  savingPassword.value = true;
  setStatus(passwordFormStatus, "正在修改密码…", "loading");
  try {
    await put(`/api/admin/users/${encodeURIComponent(passwordUsername.value)}/password`, {
      new_password: userNewPassword.value
    });
    setStatus(usersStatus, `用户 ${passwordUsername.value} 密码修改成功。`, "success");
    userNewPassword.value = "";
    userConfirmPassword.value = "";
    closeForms();
  } catch (error) {
    setStatus(passwordFormStatus, `修改密码失败：${error.message}`, "error");
  } finally {
    savingPassword.value = false;
  }
}

function onAdminMessageEnter(event) {
  if (event.shiftKey) return;
  event.preventDefault();
  if (!sendingMessage.value) void submitAdminMessage();
}

async function submitAdminMessage() {
  const content = adminMessageContent.value.trim();
  if (!content || !messageUsername.value) {
    setStatus(adminMessageStatus, "请输入消息内容。", "error");
    return;
  }
  sendingMessage.value = true;
  setStatus(adminMessageStatus, "正在发送私信…", "loading");
  try {
    await post("/api/messages", {
      recipient: messageUsername.value,
      subject: "管理员私信",
      content
    });
    adminMessageContent.value = "";
    router.push("/message");
  } catch (error) {
    setStatus(adminMessageStatus, `私信发送失败：${error.message}`, "error");
  } finally {
    sendingMessage.value = false;
  }
}

onMounted(() => {
  void loadExperimentCount();
  void loadStudentCount();
});

</script>

<template>
  <section id="adminView" class="admin-shell">
    <aside class="admin-sidebar">
      <a class="admin-logo" href="#home" @click.prevent="router.push('/home')">
        <span class="admin-logo-mark">F</span><span>Fusion <b>Lab</b></span>
      </a>
      <nav class="admin-menu" aria-label="管理端导航">
        <div class="admin-menu-group">
          <span class="admin-menu-label">系统管理</span>
          <button :class="{ active: adminSection === 'dashboard' }" @click="selectSection('dashboard')"><span class="admin-menu-icon">看</span>学习看板</button>
        </div>
        <div class="admin-menu-group">
          <span class="admin-menu-label">基础信息</span>
          <button :class="{ active: adminSection === 'users' }" @click="selectSection('users')"><span class="admin-menu-icon">学</span>学生管理</button>
          <button :class="{ active: adminSection === 'classes' }" @click="selectSection('classes')"><span class="admin-menu-icon">班</span>班级管理</button>
          <button :class="{ active: adminSection === 'roles' }" @click="selectSection('roles')"><span class="admin-menu-icon">权</span>角色管理</button>
        </div>
        <div class="admin-menu-group">
          <span class="admin-menu-label">实验管理</span>
          <button :class="{ active: adminSection === 'experiments' }" @click="selectSection('experiments')"><span class="admin-menu-icon">验</span>实验管理</button>
          <button :class="{ active: adminSection === 'experimentTypes' }" @click="selectSection('experimentTypes')"><span class="admin-menu-icon">类</span>实验类型</button>
        </div>
      </nav>
      <button class="admin-back-link" @click="router.push('/dashboard')"><span>←</span> 返回实验平台</button>
    </aside>

    <div class="admin-main">
      <header class="admin-topbar">
        <div class="admin-breadcrumb"><span>管理端</span><i>/</i><b>{{ sectionTitle }}</b></div>
        <div class="admin-top-actions">
          <button class="admin-refresh" type="button" aria-label="刷新" @click="refreshDashboard"><span>↻</span>刷新</button>
          <div class="admin-user-summary">
            <span class="admin-user-avatar">{{ auth.avatarText }}</span>
            <span><b>{{ auth.displayName }}</b><small>在线实验概览</small></span>
          </div>
        </div>
      </header>

      <main class="admin-content">
        <template v-if="adminSection === 'dashboard'">
          <div class="admin-welcome">
            <div><p class="admin-eyebrow">FUSION LAB · LEARNING CENTER</p><h1>学习看板</h1><p>欢迎回来，{{ auth.displayName }}。这里是平台实验教学概览。</p></div>
            <span class="admin-updated">更新于 {{ lastRefreshed }}</span>
          </div>
          <p v-if="dashboardStatus" class="admin-dashboard-status" role="status">{{ dashboardStatus }}</p>

          <section class="admin-stat-grid" aria-label="平台统计">
            <article v-for="stat in stats" :key="stat.label" :class="['admin-stat-card', `tone-${stat.tone}`]">
              <span class="admin-stat-icon">{{ stat.icon }}</span>
              <span class="admin-stat-label">{{ stat.label }}</span>
              <b class="admin-stat-value">{{ stat.value }}</b>
              <span class="admin-stat-foot">平台累计</span>
            </article>
          </section>

          <section class="admin-dashboard-card admin-quick-card">
            <div class="admin-card-heading"><div><h2>快捷入口</h2><p>最近访问的管理页面</p></div></div>
            <div class="admin-quick-grid">
              <button
                v-for="page in recentSectionLinks"
                :key="page.id"
                type="button"
                @click="selectSection(page.id)"
              >
                <span :class="['quick-icon', page.tone]">{{ page.icon }}</span>
                <span><b>{{ page.title }}</b><small>最近访问</small></span>
                <i>›</i>
              </button>
              <p v-if="!recentSectionLinks.length" class="admin-quick-empty">暂无最近访问页面</p>
            </div>
          </section>

          <section class="admin-dashboard-card admin-recent-experiments">
            <div class="admin-card-heading"><div><h2>最近实验</h2><p>最近添加的实验内容</p></div><button class="admin-text-link" @click="selectSection('experiments')">全部实验 <span>›</span></button></div>
            <div class="admin-table-scroll"><table class="admin-dashboard-table">
              <thead><tr><th>实验类型</th><th>实验时长</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-if="dashboardExperimentsLoading"><td colspan="3" class="admin-empty">正在加载实验数据…</td></tr>
                <tr v-else-if="dashboardExperimentsError"><td colspan="3" class="admin-empty">实验数据加载失败：{{ dashboardExperimentsError }}</td></tr>
                <tr v-else-if="!recentExperiments.length"><td colspan="3" class="admin-empty">暂无实验数据</td></tr>
                <tr v-for="experiment in recentExperiments" :key="experiment.id"><td class="table-primary">{{ experiment.experiment_type || "未设置" }}</td><td>{{ formatDuration(experiment.duration_seconds) }}</td><td><button type="button" class="admin-dashboard-edit-link" @click="selectSection('experiments')">编辑</button></td></tr>
              </tbody>
            </table></div>
          </section>

          <section class="admin-dashboard-card admin-record-card">
            <div class="admin-card-heading"><div><h2>最近实验记录</h2><p>学生近期实验运行状态</p></div></div>
            <div class="admin-table-scroll"><table class="admin-dashboard-table">
              <thead><tr><th>实验类型</th><th>操作人员</th><th>状态</th><th>时间</th></tr></thead>
              <tbody>
                <tr v-if="dashboardExperimentsLoading"><td colspan="4" class="admin-empty">正在加载实验记录…</td></tr>
                <tr v-else-if="dashboardExperimentsError"><td colspan="4" class="admin-empty">实验记录加载失败：{{ dashboardExperimentsError }}</td></tr>
                <tr v-else-if="!recentExperiments.length"><td colspan="4" class="admin-empty">暂无实验记录</td></tr>
                <tr v-for="experiment in recentExperiments" :key="`record-${experiment.id}`">
                  <td class="table-primary">{{ experiment.experiment_type || "未设置" }}</td>
                  <td>{{ experiment.operator_name || "—" }}</td>
                  <td><span :class="['admin-state-tag', experiment.is_active ? 'state-running' : 'state-missing']"><i></i>{{ experiment.is_active ? "已启用" : "已停用" }}</span></td>
                  <td>{{ formatExperimentDate(experiment.created_at) }}</td>
                </tr>
              </tbody>
            </table></div>
          </section>
        </template>

        <template v-else-if="adminSection === 'users'">
          <div class="student-management-layout">
            <aside class="student-class-sidebar" aria-label="班级筛选">
              <div class="student-class-heading"><h2>班级列表</h2><button class="class-tool-button" type="button" aria-label="刷新班级列表" title="刷新班级列表" :disabled="classesLoading" @click="loadClasses">↻</button></div>
              <label class="sr-only" for="studentClassSearch">搜索班级</label>
              <input id="studentClassSearch" v-model="classListSearch" class="student-class-search" type="search" placeholder="搜索班级">
              <nav class="student-class-list" aria-label="选择班级">
                <button type="button" :class="['student-class-item', { active: !selectedClassName }]" :aria-pressed="!selectedClassName" :title="`共 ${studentClassList.length} 个班级`" :aria-label="`全部班级，共 ${studentClassList.length} 个班级`" @click="selectedClassName = ''"><span>全部班级</span><b :title="`共 ${studentClassList.length} 个班级`">{{ studentClassList.length }}</b></button>
                <button v-for="item in filteredClasses" :key="item.id" type="button" :class="['student-class-item', { active: selectedClassName === item.name }]" :aria-pressed="selectedClassName === item.name" @click="selectedClassName = item.name"><span>{{ item.name }}</span><b>{{ classStudentCount(item.name) }}</b></button>
                <p v-if="!filteredClasses.length" class="student-class-empty">暂无匹配班级</p>
              </nav>
            </aside>

            <div class="student-management-content" :class="{ 'student-drop-active': importDragActive }" @dragenter.prevent="onImportDragOver" @dragover.prevent="onImportDragOver" @dragleave="onImportDragLeave" @drop.prevent="onImportDrop">
              <div v-if="importDragActive" class="student-drop-hint"><b>松手即可导入这个文件</b><span>支持 .xlsx 与 .csv，导入前会先显示读取到的内容</span></div>
              <header class="admin-page-heading student-page-heading"><div><p class="admin-eyebrow">BASIC INFORMATION</p><h1>学生管理</h1><p>查看学生资料，按学号、姓名或班级筛选。</p></div></header>

              <form class="student-filter-form" @submit.prevent="applyStudentFilters">
                <label>学号<input v-model="studentIdFilter" type="search" placeholder="输入学号"></label>
                <label>姓名<input v-model="studentNameFilter" type="search" placeholder="输入姓名"></label>
                <div class="student-filter-actions"><button class="btn btn-outline" type="button" @click="resetStudentFilters">重置</button><button class="btn btn-primary" type="submit">查询</button></div>
              </form>

              <p :class="usersStatusClass" id="usersStatus" role="status" aria-live="polite">{{ usersStatus }}</p>

              <section class="student-list-panel" aria-labelledby="studentListTitle">
                <div class="student-table-toolbar">
                  <h2 id="studentListTitle">学生列表 <span>{{ filteredUsers.length }}</span></h2>
                  <div class="student-table-tools">
                    <span v-if="selectedStudentUsernames.length" class="student-selection-count">已选 {{ selectedStudentUsernames.length }} 位</span>
                    <button class="btn btn-outline student-tool-text" type="button" :disabled="!selectedStudentUsernames.length || studentBatchDeleting || studentBatchEditing" @click="openStudentBatchEdit">批量编辑</button>
                    <button class="btn btn-outline student-tool-text student-batch-delete" type="button" :disabled="!selectedStudentUsernames.length || studentBatchDeleting || studentBatchEditing" @click="batchDeleteStudents">{{ studentBatchDeleting ? "删除中…" : "批量删除" }}</button>
                    <button class="btn btn-primary student-add-button" id="showCreateUser" type="button" @click="openCreateForm">＋ 新增学生</button>
                    <button class="btn btn-outline student-tool-text" type="button" title="下载 CSV 模板，可用 Excel/WPS 打开编辑后直接导入" @click="downloadImportTemplate">导入模板下载</button>
                    <button class="btn btn-outline student-tool-text" type="button" title="支持 Excel (.xlsx) 与 CSV 文件，也可以直接把文件拖到本页" :disabled="importingStudents" @click="studentImportInput?.click()">{{ importingStudents ? "导入中…" : "导入学生" }}</button>
                    <button class="btn btn-outline student-tool-text" type="button" @click="exportStudents">导出学生信息</button>
                    <button class="class-tool-button" type="button" aria-label="刷新学生列表" title="刷新" @click="loadUsers">↻</button>
                    <div class="class-column-control">
                      <button class="class-tool-button" type="button" aria-label="列设置" title="列设置" :aria-expanded="showStudentColumnSettings" @click="showStudentColumnSettings = !showStudentColumnSettings">▤</button>
                      <div v-if="showStudentColumnSettings" class="class-column-menu">
                        <label v-for="column in studentColumns" :key="column.key"><input v-model="column.visible" type="checkbox">{{ column.label }}</label>
                      </div>
                    </div>
                    <button class="class-tool-button" type="button" aria-label="切换紧凑行距" title="紧凑行距" :aria-pressed="compactStudentTable" @click="compactStudentTable = !compactStudentTable">⚙</button>
                    <input ref="studentImportInput" class="hidden" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-hidden="true" tabindex="-1" @change="importStudents">
                  </div>
                </div>

                <div class="student-table-scroll">
                  <table class="student-list-table" :class="{ 'student-table-compact': compactStudentTable }">
                    <thead><tr><th><input type="checkbox" aria-label="选择当前筛选的学生" :checked="allFilteredStudentsSelected" :disabled="usersStatusState === 'loading' || studentBatchDeleting || studentBatchEditing || !filteredUsers.length" @change="toggleFilteredStudentSelection"></th><th>序号</th><th v-for="column in visibleStudentColumns" :key="column.key">{{ column.label }}</th><th>操作</th></tr></thead>
                    <tbody>
                      <tr v-if="usersStatusState === 'loading'"><td :colspan="visibleStudentColumns.length + 3" class="admin-empty">正在加载学生列表…</td></tr>
                      <tr v-else-if="!filteredUsers.length"><td :colspan="visibleStudentColumns.length + 3" class="admin-empty">{{ emptyText }}</td></tr>
                      <template v-else>
                        <tr v-for="(item, index) in filteredUsers" :key="item.username">
                          <td><input type="checkbox" :aria-label="`选择学生 ${item.display_name || item.username}`" :checked="selectedStudentUsernames.includes(item.username)" :disabled="studentBatchDeleting || studentBatchEditing" @change="toggleStudentSelection(item.username)"></td>
                          <td>{{ index + 1 }}</td>
                          <td v-for="column in visibleStudentColumns" :key="column.key" :class="{ 'student-name-cell': column.key === 'display_name' }">{{ studentCellValue(item, column.key) }}</td>
                          <td class="student-row-actions">
                            <button type="button" class="class-row-action class-row-message" :aria-label="`给学生 ${item.display_name || item.username} 发私信`" title="私信" @click="onAction('message', item)">✉</button>
                            <button type="button" class="class-row-action" :aria-label="`编辑学生 ${item.display_name || item.username}`" title="编辑" @click="onAction('edit', item)">✎</button>
                            <button type="button" class="class-row-action class-row-delete" :aria-label="`删除学生 ${item.display_name || item.username}`" title="删除" @click="onAction('delete', item)">×</button>
                          </td>
                        </tr>
                      </template>
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          </div>
          <section class="account-card admin-card admin-user-form" :class="{ hidden: !messageFormOpen }" id="messagePanel">
            <h2 id="messageFormTitle">{{ messageFormTitle }}</h2>
            <form id="adminMessageForm" @submit.prevent="submitAdminMessage">
              <div class="field"><label for="adminMessageContent">消息内容</label><textarea id="adminMessageContent" v-model="adminMessageContent" rows="4" maxlength="2000" required placeholder="输入要发送给用户的私信" @keydown.enter="onAdminMessageEnter"></textarea></div>
              <div class="admin-form-actions"><button class="btn btn-primary" type="submit" id="sendAdminMessage" :disabled="sendingMessage">发送私信</button><button class="btn btn-outline" type="button" id="cancelAdminMessage" @click="closeForms">取消</button></div>
              <p :class="adminMessageStatusClass" id="adminMessageStatus" role="status" aria-live="polite">{{ adminMessageStatus }}</p>
            </form>
          </section>
          <section class="account-card admin-card admin-user-form" :class="{ hidden: !userFormOpen }" id="userFormPanel">
            <h2 id="userFormTitle">{{ userFormTitle }}</h2>
            <form id="userForm" @submit.prevent="submitUserForm">
              <div class="field"><label for="userAccount">账号（学号）</label><input id="userAccount" v-model="userAccount" name="username" inputmode="numeric" pattern="[0-9]+" autocomplete="off" required :readonly="!!editingUsername"></div>
              <div class="field"><label for="userDisplayName">自定义名称</label><input id="userDisplayName" v-model="userDisplayName" name="display_name" maxlength="40" required></div>
              <div class="field">
                <label for="userClassName">所属班级</label>
                <input id="userClassName" v-model="userClassName" name="class_name" list="studentClassOptions" maxlength="128" autocomplete="off" placeholder="选择已有班级，或直接输入新班级名">
                <datalist id="studentClassOptions">
                  <option v-for="item in studentClassList" :key="item.id" :value="item.name">{{ item.grade || "年级未维护" }}</option>
                </datalist>
                <p class="class-name-hint">输入系统中没有的班级名，保存后会自动在「班级管理」创建（年级默认「未设置」，可稍后修改）；留空表示未分班。</p>
              </div>
              <div class="field" id="initialPasswordField" :class="{ hidden: !!editingUsername }"><label for="userPassword">初始密码</label><input id="userPassword" v-model="userPassword" name="password" type="password" minlength="8" autocomplete="new-password" :required="!editingUsername"></div>
              <div class="admin-form-actions"><button class="btn btn-primary" type="submit" id="saveUserButton" :disabled="savingUser">{{ editingUsername ? "保存修改" : "创建用户" }}</button><button class="btn btn-outline" type="button" id="cancelUserForm" @click="closeForms">取消</button></div>
              <p :class="userFormStatusClass" id="userFormStatus" role="status" aria-live="polite">{{ userFormStatus }}</p>
            </form>
          </section>
          <section class="account-card admin-card admin-user-form" :class="{ hidden: !passwordFormOpen }" id="passwordPanel">
            <h2 id="passwordFormTitle">{{ passwordFormTitle }}</h2>
            <form id="passwordForm" @submit.prevent="submitPasswordForm">
              <div class="field"><label for="userNewPassword">新密码</label><input id="userNewPassword" v-model="userNewPassword" type="password" minlength="8" autocomplete="new-password" required></div>
              <div class="field"><label for="userConfirmPassword">确认新密码</label><input id="userConfirmPassword" v-model="userConfirmPassword" type="password" minlength="8" autocomplete="new-password" required></div>
              <div class="admin-form-actions"><button class="btn btn-primary" type="submit" :disabled="savingPassword">确认修改</button><button class="btn btn-outline" type="button" id="cancelPasswordForm" @click="closeForms">取消</button></div>
              <p :class="passwordFormStatusClass" id="passwordFormStatus" role="status" aria-live="polite">{{ passwordFormStatus }}</p>
            </form>
          </section>
          <div v-if="studentBatchEditOpen" class="class-modal-backdrop" @click.self="closeStudentBatchEdit">
            <section class="class-modal" role="dialog" aria-modal="true" aria-labelledby="studentBatchEditTitle">
              <header><div><p class="admin-eyebrow">STUDENT EDIT</p><h2 id="studentBatchEditTitle">{{ studentBatchEditUsernames.length === 1 ? "编辑学生" : "批量编辑学生" }}</h2></div><button type="button" class="class-modal-close" aria-label="关闭" :disabled="studentBatchEditing" @click="closeStudentBatchEdit">×</button></header>
              <form @submit.prevent="saveStudentBatchEdit">
                <div class="class-form-grid">
                  <label class="student-batch-class-toggle"><input v-model="studentBatchChangeClass" type="checkbox">同时调整所属班级</label>
                  <label class="class-form-remark">目标班级（{{ studentBatchEditUsernames.length }} 位学生）
                    <input v-model="studentBatchClassName" list="studentClassOptions" maxlength="128" autocomplete="off" :disabled="!studentBatchChangeClass" placeholder="选择或输入班级名；留空表示未分班">
                  </label>
                  <label class="class-form-remark">年级（可选）
                    <input v-model="studentBatchGrade" maxlength="32" autocomplete="off" placeholder="输入年级">
                  </label>
                  <label class="student-batch-class-toggle"><input v-model="studentBatchResetPassword" type="checkbox">同时重置学生密码</label>
                  <label class="class-form-remark">统一新密码
                    <input v-model="studentBatchNewPassword" type="password" minlength="8" autocomplete="new-password" placeholder="至少 8 位" @focus="studentBatchResetPassword = true">
                  </label>
                </div>
                <p class="class-name-hint">勾选班级调整后，学生将统一加入目标班级；输入新班级名会自动创建。填写年级会更新目标班级；未指定目标班级时，会更新所选学生当前所属班级的年级，影响这些班级内的所有学生。点击新密码输入框会自动启用批量重置密码。</p>
                <p v-if="studentBatchEditError" class="status error" role="alert">{{ studentBatchEditError }}</p>
                <footer><button class="btn btn-outline" type="button" :disabled="studentBatchEditing" @click="closeStudentBatchEdit">取消</button><button class="btn btn-primary" type="submit" :disabled="studentBatchEditing">{{ studentBatchEditing ? "保存中…" : studentBatchEditUsernames.length === 1 ? "保存修改" : "应用到已选学生" }}</button></footer>
              </form>
            </section>
          </div>
        </template>

        <template v-else-if="adminSection === 'classes'">
          <header class="admin-page-heading class-page-heading">
            <div><p class="admin-eyebrow">BASIC INFORMATION</p><h1>班级管理</h1><p>维护班级基础资料、年级和显示顺序；人数由学生列表自动统计。</p></div>
          </header>

          <section class="class-management-card" aria-labelledby="classListTitle">
            <form class="class-filter-form" @submit.prevent="loadClasses">
              <label>班级名称<input v-model="classNameFilter" type="search" placeholder="输入班级名称"></label>
              <label>年级<input v-model="classGradeFilter" type="search" placeholder="输入年级"></label>
              <div class="class-filter-actions">
                <button class="btn btn-outline" type="button" @click="resetClassFilters">重置</button>
                <button class="btn btn-primary" type="submit" :disabled="classesLoading">查询</button>
              </div>
            </form>

            <p :class="['status', classesStatusState]" role="status" aria-live="polite">{{ classesStatus }}</p>

            <div class="class-table-toolbar">
              <h2 id="classListTitle">班级列表 <span>{{ classes.length }}</span></h2>
              <div class="class-table-tools">
                <button class="class-tool-button" type="button" aria-label="刷新班级列表" title="刷新" :disabled="classesLoading" @click="loadClasses">↻</button>
                <div class="class-column-control">
                  <button class="class-tool-button" type="button" aria-label="列设置" title="列设置" :aria-expanded="showClassColumnSettings" @click="showClassColumnSettings = !showClassColumnSettings">▤</button>
                  <div v-if="showClassColumnSettings" class="class-column-menu">
                    <label v-for="column in classColumnOptions" :key="column.key"><input v-model="column.visible" type="checkbox">{{ column.label }}</label>
                  </div>
                </div>
                <button class="class-tool-button" type="button" aria-label="切换紧凑行距" title="紧凑行距" :aria-pressed="compactClassTable" @click="compactClassTable = !compactClassTable">⚙</button>
                <button class="btn btn-primary class-add-button" type="button" @click="openClassForm()"><span aria-hidden="true">＋</span> 新增班级</button>
              </div>
            </div>

            <div class="class-table-scroll">
              <table class="class-table" :class="{ 'class-table-compact': compactClassTable }">
                <thead><tr><th v-for="column in visibleClassColumns" :key="column.key" :title="column.key === 'student_count' ? '按学生列表自动统计' : undefined">{{ column.label }}</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-if="classesLoading"><td :colspan="visibleClassColumns.length + 1" class="admin-empty">正在加载班级列表…</td></tr>
                  <tr v-else-if="!classes.length"><td :colspan="visibleClassColumns.length + 1" class="admin-empty">暂无班级数据</td></tr>
                  <template v-else>
                    <tr v-for="item in classes" :key="item.id">
                      <td v-for="column in visibleClassColumns" :key="column.key" :class="{ 'class-name-cell': column.key === 'name' }">
                        {{ column.key === "created_at" ? formatClassDate(item[column.key]) : item[column.key] ?? "—" }}
                      </td>
                      <td class="class-row-actions">
                        <button type="button" class="class-row-action" :aria-label="`编辑班级 ${item.name}`" title="编辑" @click="openClassForm(item)">✎</button>
                        <button type="button" class="class-row-action class-row-delete" :aria-label="`删除班级 ${item.name}`" title="删除" :disabled="classActionId === item.id" @click="deleteClass(item)">×</button>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </section>

          <div v-if="classFormOpen" class="class-modal-backdrop" @click.self="closeClassForm">
            <section class="class-modal" role="dialog" aria-modal="true" aria-labelledby="classFormTitle">
              <header><div><p class="admin-eyebrow">CLASS INFORMATION</p><h2 id="classFormTitle">{{ classEditingId ? "编辑班级" : "新增班级" }}</h2></div><button type="button" class="class-modal-close" aria-label="关闭" @click="closeClassForm">×</button></header>
              <form @submit.prevent="saveClass">
                <div class="class-form-grid">
                  <label>班级名称<input v-model="classForm.name" maxlength="128" required placeholder="如：人工智能 1 班"></label>
                  <label>年级<input v-model="classForm.grade" maxlength="32" required placeholder="如：2026 级"></label>
                  <label>人数（自动统计）<input :value="classForm.student_count" class="class-auto-count" type="number" min="0" step="1" readonly tabindex="-1" title="人数由学生列表自动统计，不可手动修改"></label>
                  <label>排序<input v-model.number="classForm.sort_order" type="number" min="0" step="1" required></label>
                  <label class="class-form-remark">备注<textarea v-model="classForm.remark" maxlength="500" rows="3" placeholder="可填写班级说明"></textarea></label>
                </div>
                <p v-if="classEditingId" class="class-rename-hint">修改班级名称后，该班学生的「所属班级」会同步更新；人数始终按学生列表自动统计。</p>
                <footer><button type="button" class="btn btn-outline" @click="closeClassForm">取消</button><button type="submit" class="btn btn-primary" :disabled="classSaving">{{ classSaving ? "保存中…" : "保存班级" }}</button></footer>
              </form>
            </section>
          </div>
        </template>

        <template v-else-if="adminSection === 'roles'">
          <header class="admin-page-heading">
            <div><p class="admin-eyebrow">BASIC INFORMATION</p><h1>角色管理</h1><p>管理普通用户的管理员权限及管理员账号状态。</p></div>
            <button class="btn btn-outline" type="button" aria-label="刷新角色信息" :disabled="loadingRoles" @click="loadRoles">{{ loadingRoles ? "刷新中…" : "刷新" }}</button>
          </header>
          <p :class="rolesStatusClass" role="status" aria-live="polite">{{ rolesStatus }}</p>
          <div class="admin-role-columns">
            <section class="admin-dashboard-card admin-role-list-card" aria-labelledby="adminRoleUsersTitle">
              <header class="admin-card-heading"><div><h2 id="adminRoleUsersTitle">管理员（{{ roleCounts.admin }}）</h2></div></header>
              <div class="admin-table-scroll">
                <table class="admin-dashboard-table admin-role-table">
                  <thead><tr><th>用户名称</th><th>状态</th></tr></thead>
                  <tbody>
                    <tr v-if="loadingRoles"><td colspan="2" class="admin-empty">正在加载管理员…</td></tr>
                    <tr v-else-if="!hasRolesData"><td colspan="2" class="admin-empty">管理员列表加载失败</td></tr>
                    <tr v-else-if="!roleUsers.some((user) => user.role === 'admin')"><td colspan="2" class="admin-empty">暂无管理员</td></tr>
                    <tr v-for="user in roleUsers.filter((item) => item.role === 'admin')" :key="user.username">
                      <td class="table-primary">{{ user.display_name || user.username }}</td>
                      <td>
                        <button
                          :class="['admin-role-toggle', user.is_active ? 'is-enabled' : 'is-disabled']"
                          type="button"
                          :disabled="!!roleActionUsername || user.username === auth.user.username"
                          :aria-label="`${user.is_active ? '停用' : '启用'}管理员 ${user.display_name || user.username}`"
                          :aria-pressed="user.is_active"
                          :title="user.username === auth.user.username ? '不能更改当前登录管理员的状态' : `${user.is_active ? '停用' : '启用'}该管理员`"
                          @click="toggleAdminStatus(user)"
                        >
                          <span class="admin-role-switch" aria-hidden="true"><span></span></span>
                          <span>{{ roleActionUsername === user.username ? "处理中…" : user.is_active ? "已启用" : "已停用" }}</span>
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
            <section class="admin-dashboard-card admin-role-list-card" aria-labelledby="ordinaryRoleUsersTitle">
              <header class="admin-card-heading"><div><h2 id="ordinaryRoleUsersTitle">普通用户（{{ roleCounts.user }}）</h2></div></header>
              <div class="admin-table-scroll">
                <table class="admin-dashboard-table admin-role-table">
                  <thead><tr><th>用户名称</th><th>操作</th></tr></thead>
                  <tbody>
                    <tr v-if="loadingRoles"><td colspan="2" class="admin-empty">正在加载用户…</td></tr>
                    <tr v-else-if="!hasRolesData"><td colspan="2" class="admin-empty">用户列表加载失败</td></tr>
                    <tr v-else-if="!roleUsers.some((user) => user.role === 'user')"><td colspan="2" class="admin-empty">暂无普通用户</td></tr>
                    <tr v-for="user in roleUsers.filter((item) => item.role === 'user')" :key="user.username">
                      <td class="table-primary">{{ user.display_name || user.username }}</td>
                      <td><button class="admin-row-action" type="button" :disabled="!!roleActionUsername" @click="promoteUserToAdmin(user)">{{ roleActionUsername === user.username ? "处理中…" : "编辑" }}</button></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </template>

        <template v-else-if="adminSection === 'experiments'">
          <header class="admin-page-heading experiment-page-heading">
            <div><p class="admin-eyebrow">EXPERIMENT MANAGEMENT</p><h1>实验管理</h1><p>查看实验运行参数，维护实验记录和启用状态。</p></div>
            <button class="btn btn-primary" type="button" @click="openExperimentForm()"><span aria-hidden="true">＋</span> 新增实验</button>
          </header>

          <section class="experiment-toolbar" aria-label="实验搜索">
            <form class="experiment-search" @submit.prevent="loadExperiments()">
              <label class="sr-only" for="experimentKeyword">实验名称</label>
              <input id="experimentKeyword" v-model="experimentKeyword" type="search" placeholder="请输入实验名称">
              <label class="sr-only" for="experimentTypeFilter">实验类型</label>
              <select id="experimentTypeFilter" v-model="experimentTypeFilter" aria-label="按实验类型筛选">
                <option value="">全部实验类型</option>
                <option v-for="type in experimentTypes" :key="type" :value="type">{{ type }}</option>
              </select>
              <button class="btn btn-outline" type="button" @click="resetExperimentSearch">重置</button>
              <button class="btn btn-primary" type="submit" :disabled="experimentLoading">查询</button>
            </form>
          </section>

          <p :class="['status', experimentStatusState]" role="status" aria-live="polite">{{ experimentStatus }}</p>

          <section class="admin-dashboard-card experiment-list-card" aria-labelledby="experimentListTitle">
            <div class="experiment-list-heading">
              <h2 id="experimentListTitle">实验列表</h2>
              <div class="experiment-batch-actions">
                <span>当前筛选 {{ experiments.length }} 条 · 已选 {{ selectedExperimentIds.length }} 条</span>
                <button class="btn btn-outline" type="button" :disabled="!selectedExperimentIds.length || experimentBatchDeleting || experimentLoading" @click="batchDeleteExperiments">
                  {{ experimentBatchDeleting ? "删除中…" : "批量删除" }}
                </button>
              </div>
            </div>
            <div class="admin-table-scroll experiment-table-scroll">
              <table class="admin-dashboard-table experiment-table">
                <thead><tr><th><input type="checkbox" aria-label="选择当前页实验" :checked="allVisibleExperimentsSelected" :disabled="experimentLoading || experimentBatchDeleting || !visibleExperiments.length" @change="toggleVisibleExperimentSelection"></th><th>实验名称</th><th>实验类型</th><th>实验时长</th><th>车辆速度</th><th>加速度</th><th>油门</th><th>车辆朝向</th><th>前视流帧率</th><th>创建时间</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-if="experimentLoading"><td colspan="11" class="admin-empty">正在读取数据库记录…</td></tr>
                  <tr v-else-if="!visibleExperiments.length"><td colspan="11" class="admin-empty">{{ experimentKeyword || experimentTypeFilter ? "没有匹配的实验记录" : "数据库中暂无实验记录" }}</td></tr>
                  <tr v-for="item in visibleExperiments" :key="item.id">
                    <td><input type="checkbox" :aria-label="`选择实验 ${item.name}`" :checked="selectedExperimentIds.includes(item.id)" :disabled="experimentBatchDeleting" @change="toggleExperimentSelection(item.id)"></td>
                    <td class="experiment-name-cell"><strong>{{ item.name }}</strong><span :class="['experiment-state', item.is_active ? 'is-active' : 'is-inactive']">{{ item.is_active ? "已启用" : "已停用" }}</span></td>
                    <td>{{ item.experiment_type || "未设置" }}</td>
                    <td>{{ formatDuration(item.duration_seconds) }}</td>
                    <td>{{ Number(item.speed || 0).toFixed(1) }} <small>km/h</small></td>
                    <td>{{ Number(item.acceleration || 0).toFixed(2) }} <small>m/s²</small></td>
                    <td>{{ Number(item.throttle || 0).toFixed(1) }}<small>%</small></td>
                    <td>{{ Number(item.yaw || 0).toFixed(1) }}<small>°</small></td>
                    <td>{{ Number(item.front_fps || 0).toFixed(1) }} <small>fps</small></td>
                    <td>{{ formatExperimentDate(item.created_at) }}</td>
                    <td class="experiment-actions">
                      <button type="button" class="experiment-icon-action" :aria-label="`查看 ${item.name}`" title="查看" @click="experimentToView = item">◉</button>
                      <button v-if="!item.is_active" type="button" class="experiment-icon-action action-start" :aria-label="`启动 ${item.name}`" title="启动" :disabled="experimentBatchDeleting || experimentActionId === item.id" @click="toggleExperiment(item)">▶</button>
                      <button v-else type="button" class="experiment-icon-action action-stop" :aria-label="`停用 ${item.name}`" title="停用" :disabled="experimentBatchDeleting || experimentActionId === item.id" @click="toggleExperiment(item)">■</button>
                      <button type="button" class="experiment-icon-action" :aria-label="`编辑 ${item.name}`" title="编辑" @click="openExperimentForm(item)">✎</button>
                      <button type="button" class="experiment-icon-action action-delete" :aria-label="`删除 ${item.name}`" title="删除" :disabled="experimentBatchDeleting || experimentActionId === item.id" @click="deleteExperiment(item)">×</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <footer class="experiment-pagination">
              <span>第 {{ experimentPage }} / {{ experimentPageCount }} 页，共 {{ experiments.length }} 条</span>
              <div>
                <button type="button" class="btn btn-outline" aria-label="上一页" :disabled="experimentPage <= 1" @click="experimentPage -= 1">上一页</button>
                <button type="button" class="btn btn-outline" aria-label="下一页" :disabled="experimentPage >= experimentPageCount" @click="experimentPage += 1">下一页</button>
              </div>
            </footer>
          </section>

          <div v-if="experimentFormOpen" class="experiment-modal-backdrop" @click.self="closeExperimentForm">
            <section class="experiment-modal" role="dialog" aria-modal="true" aria-labelledby="experimentFormTitle">
              <header><div><p class="admin-eyebrow">EXPERIMENT DATA</p><h2 id="experimentFormTitle">{{ experimentEditingId ? "编辑实验" : "新增实验" }}</h2></div><button type="button" class="experiment-modal-close" aria-label="关闭" @click="closeExperimentForm">×</button></header>
              <form @submit.prevent="saveExperiment">
                <div class="experiment-form-grid">
                  <label class="experiment-form-name">实验名称<input v-model="experimentForm.name" maxlength="128" required placeholder="输入实验名称"></label>
                  <label>实验类型
                    <input v-model="experimentForm.experiment_type" list="experimentTypeOptions" maxlength="64" required placeholder="输入或选择实验类型">
                    <datalist id="experimentTypeOptions">
                      <option v-for="type in experimentTypes" :key="type" :value="type">{{ type }}</option>
                    </datalist>
                  </label>
                  <label class="experiment-form-description">实验简介
                    <textarea v-model="experimentForm.description" maxlength="2000" rows="5" required placeholder="请简要介绍实验内容"></textarea>
                  </label>
                </div>
                <footer><button type="button" class="btn btn-outline" @click="closeExperimentForm">取消</button><button type="submit" class="btn btn-primary" :disabled="experimentSaving">{{ experimentSaving ? "保存中…" : "保存实验" }}</button></footer>
              </form>
            </section>
          </div>

          <div v-if="experimentToView" class="experiment-modal-backdrop" @click.self="experimentToView = null">
            <section class="experiment-modal experiment-detail-modal" role="dialog" aria-modal="true" aria-labelledby="experimentDetailTitle">
              <header><div><p class="admin-eyebrow">EXPERIMENT DETAIL</p><h2 id="experimentDetailTitle">{{ experimentToView.name }}</h2></div><button type="button" class="experiment-modal-close" aria-label="关闭" @click="experimentToView = null">×</button></header>
              <dl class="experiment-detail-grid">
                <div><dt>实验类型</dt><dd>{{ experimentToView.experiment_type || "未设置" }}</dd></div>
                <div class="experiment-detail-description"><dt>实验简介</dt><dd>{{ experimentToView.description || "暂无简介" }}</dd></div>
                <div><dt>实验时长</dt><dd>{{ formatDuration(experimentToView.duration_seconds) }}</dd></div>
                <div><dt>车辆速度</dt><dd>{{ Number(experimentToView.speed || 0).toFixed(1) }} km/h</dd></div>
                <div><dt>加速度</dt><dd>{{ Number(experimentToView.acceleration || 0).toFixed(2) }} m/s²</dd></div>
                <div><dt>油门</dt><dd>{{ Number(experimentToView.throttle || 0).toFixed(1) }}%</dd></div>
                <div><dt>车辆朝向</dt><dd>{{ Number(experimentToView.yaw || 0).toFixed(1) }}°</dd></div>
                <div><dt>前视流帧率</dt><dd>{{ Number(experimentToView.front_fps || 0).toFixed(1) }} fps</dd></div>
                <div><dt>创建时间</dt><dd>{{ formatExperimentDate(experimentToView.created_at) }}</dd></div>
                <div><dt>运行状态</dt><dd>{{ experimentToView.is_active ? "已启用" : "已停用" }}</dd></div>
              </dl>
              <footer><button type="button" class="btn btn-primary" @click="experimentToView = null">关闭</button></footer>
            </section>
          </div>
        </template>

        <template v-else-if="adminSection === 'experimentTypes'">
          <header class="type-page-heading">
            <div>
              <p class="admin-eyebrow">EXPERIMENT MANAGEMENT</p>
              <h1>实验类型</h1>
              <p>维护实验分类的名称、显示顺序与备注，供实验管理中的类型选择使用。</p>
            </div>
            <div class="type-page-tools">
              <button class="btn btn-primary type-add-button" type="button" @click="openTypeForm()"><span aria-hidden="true">＋</span> 新增分类</button>
              <button class="type-tool-button" type="button" title="刷新" aria-label="刷新实验类型" :disabled="typeLoading" @click="loadExperimentTypes">↻</button>
              <div class="type-menu-control">
                <button class="type-tool-button" type="button" title="导入导出" aria-label="导入导出" :aria-expanded="showTypeExportMenu" @click="toggleTypeMenu('export')">⇅</button>
                <div v-if="showTypeExportMenu" class="type-menu" role="menu">
                  <button type="button" role="menuitem" @click="exportTypes">导出实验类型</button>
                  <button type="button" role="menuitem" :disabled="importingTypes" @click="closeTypeMenus(); typeImportInput?.click()">{{ importingTypes ? "导入中…" : "导入实验类型" }}</button>
                  <button type="button" role="menuitem" @click="downloadTypeTemplate">下载导入模板</button>
                </div>
              </div>
              <div class="type-menu-control">
                <button class="type-tool-button" type="button" title="设置" aria-label="设置" :aria-expanded="showTypeSettings" @click="toggleTypeMenu('settings')">⚙</button>
                <div v-if="showTypeSettings" class="type-menu type-settings-menu">
                  <span class="type-menu-label">显示列</span>
                  <label v-for="column in typeColumns" :key="column.key"><input v-model="column.visible" type="checkbox">{{ column.label }}</label>
                  <label class="type-menu-divider"><input v-model="compactTypeTable" type="checkbox">紧凑行距</label>
                </div>
              </div>
              <input ref="typeImportInput" class="hidden" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-hidden="true" tabindex="-1" @change="importTypes">
            </div>
          </header>
          <div v-if="showTypeExportMenu || showTypeSettings" class="type-menu-backdrop" @click="closeTypeMenus"></div>

          <p :class="['status', typeStatusState]" role="status" aria-live="polite">{{ typeStatus }}</p>

          <section class="type-list-card" aria-labelledby="typeListTitle">
            <h2 id="typeListTitle" class="type-list-title">类型列表 <span>{{ typeRecords.length }}</span></h2>
            <div class="class-table-scroll">
              <table class="class-table type-table" :class="{ 'class-table-compact': compactTypeTable }">
                <thead><tr><th v-for="column in visibleTypeColumns" :key="column.key">{{ column.label }}</th><th class="type-actions-head">操作</th></tr></thead>
                <tbody>
                  <tr v-if="typeLoading"><td :colspan="visibleTypeColumns.length + 1" class="admin-empty">正在加载实验类型…</td></tr>
                  <tr v-else-if="!typeRecords.length"><td :colspan="visibleTypeColumns.length + 1" class="admin-empty">数据库中暂无实验类型，点击「新增分类」添加</td></tr>
                  <template v-else>
                    <tr v-for="item in typeRecords" :key="item.id">
                      <td v-for="column in visibleTypeColumns" :key="column.key" :class="{ 'class-name-cell': column.key === 'name', 'type-remark-cell': column.key === 'remark' }">{{ typeCellValue(item, column.key) }}</td>
                      <td class="type-row-actions">
                        <button type="button" class="type-row-action type-row-add" :aria-label="`在 ${item.name} 后新增分类`" title="新增分类" @click="openTypeForm(null, item)">＋</button>
                        <button type="button" class="type-row-action type-row-edit" :aria-label="`编辑 ${item.name}`" title="编辑" @click="openTypeForm(item)">✎</button>
                        <button type="button" class="type-row-action type-row-delete" :aria-label="`删除 ${item.name}`" title="删除" :disabled="typeActionId === item.id" @click="deleteType(item)">×</button>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </section>

          <div v-if="typeFormOpen" class="class-modal-backdrop" @click.self="closeTypeForm">
            <section class="class-modal" role="dialog" aria-modal="true" aria-labelledby="typeFormTitle">
              <header><div><p class="admin-eyebrow">EXPERIMENT TYPE</p><h2 id="typeFormTitle">{{ typeEditingId ? "编辑实验类型" : "新增分类" }}</h2></div><button type="button" class="class-modal-close" aria-label="关闭" @click="closeTypeForm">×</button></header>
              <form @submit.prevent="saveType">
                <div class="class-form-grid">
                  <label>实验类型名称<input v-model="typeForm.name" maxlength="128" required placeholder="如：智能汽车视觉感知实验"></label>
                  <label>排序<input v-model.number="typeForm.sort_order" type="number" min="0" step="1" required></label>
                  <label class="class-form-remark">备注<textarea v-model="typeForm.remark" maxlength="500" rows="3" placeholder="可填写该实验类型的适用场景"></textarea></label>
                </div>
                <footer><button type="button" class="btn btn-outline" @click="closeTypeForm">取消</button><button type="submit" class="btn btn-primary" :disabled="typeSaving">{{ typeSaving ? "保存中…" : "保存" }}</button></footer>
              </form>
            </section>
          </div>
        </template>

        <section v-else class="admin-dashboard-card admin-empty-state">
          <span class="admin-empty-icon">{{ adminSection === 'experiments' ? '验' : '课' }}</span>
          <h1>{{ sectionTitle }}</h1>
          <p>该管理模块目前尚未接入业务接口，学习看板中的示例数据仅用于展示。</p>
          <button class="btn btn-outline" @click="selectSection('dashboard')">返回学习看板</button>
        </section>
      </main>
    </div>
  </section>
</template>
