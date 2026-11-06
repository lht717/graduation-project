<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
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
  basics: "基础信息"
};
const sectionTitle = computed(() => sectionTitles[adminSection.value] || "学习看板");

const experimentTotal = ref(null);
const stats = computed(() => [
  { label: "实验", value: experimentTotal.value ?? "—", tone: "violet", icon: "验" },
  { label: "学生", value: 2, tone: "green", icon: "学" }
]);
const recentExperiments = [];
const recentRecords = [];

const users = ref([]);
const usersStatus = ref("");
const usersStatusState = ref("");
const studentIdFilter = ref("");
const studentNameFilter = ref("");
const appliedStudentId = ref("");
const appliedStudentName = ref("");
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
const experimentFormOpen = ref(false);
const experimentSaving = ref(false);
const experimentEditingId = ref(null);
const experimentActionId = ref(null);
const experimentToView = ref(null);
const experimentForm = ref({
  name: "",
  duration_seconds: 0,
  speed: 0,
  acceleration: 0,
  throttle: 0,
  yaw: 0,
  front_fps: 0
});
const roleUsers = ref([]);
const rolesStatus = ref("");
const rolesStatusState = ref("");
const loadingRoles = ref(false);
const hasRolesData = ref(false);

const systemRoles = [
  { role: "admin", name: "管理员", description: "管理学生账号、平台基础信息与实验教学内容。" },
  { role: "user", name: "普通用户", description: "登录实验平台，查看实验并使用已开放的实验工作台。" }
];

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

async function loadExperiments(keyword = experimentKeyword.value.trim()) {
  experimentLoading.value = true;
  setExperimentStatus("正在加载实验列表…", "loading");
  try {
    const result = await get(`/api/admin/experiments?keyword=${encodeURIComponent(keyword)}`);
    if (!Array.isArray(result.experiments)) throw new Error("实验列表格式不正确");
    experiments.value = result.experiments;
    if (!keyword) experimentTotal.value = result.experiments.length;
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
  try {
    const result = await get("/api/admin/experiments");
    if (Array.isArray(result.experiments)) experimentTotal.value = result.experiments.length;
  } catch {
    experimentTotal.value = null;
  }
}

function resetExperimentSearch() {
  experimentKeyword.value = "";
  void loadExperiments("");
}

function openExperimentForm(item = null) {
  experimentEditingId.value = item?.id ?? null;
  experimentForm.value = item
    ? {
        name: item.name || "",
        duration_seconds: item.duration_seconds || 0,
        speed: item.speed || 0,
        acceleration: item.acceleration || 0,
        throttle: item.throttle || 0,
        yaw: item.yaw || 0,
        front_fps: item.front_fps || 0
      }
    : { name: "", duration_seconds: 0, speed: 0, acceleration: 0, throttle: 0, yaw: 0, front_fps: 0 };
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
  if (!payload.name) {
    setExperimentStatus("请输入实验名称。", "error");
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
    setExperimentStatus("实验记录已删除。", "success");
  } catch (error) {
    setExperimentStatus(`删除失败：${error.message}`, "error");
  } finally {
    experimentActionId.value = null;
  }
}

function selectSection(section) {
  adminSection.value = section;
  dashboardStatus.value = "";
  if (section === "users") {
    void loadUsers();
    void loadClasses();
  }
  if (section === "classes") void loadClasses();
  if (section === "roles") void loadRoles();
  if (section === "experiments") void loadExperiments();
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
  else dashboardStatus.value = "当前展示示例数据，尚未连接看板数据接口。";
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
    setStatus(usersStatus, `加载成功，共 ${users.value.length} 位普通用户。`, "success");
  } catch (error) {
    users.value = [];
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
    const result = await get(`/api/admin/classes?${params}`);
    if (!Array.isArray(result.classes)) throw new Error("班级列表格式不正确");
    classes.value = result.classes;
    setClassesStatus(`共 ${classes.value.length} 个班级。`, "success");
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
  const payload = {
    ...classForm.value,
    name: classForm.value.name.trim(),
    grade: classForm.value.grade.trim(),
    remark: classForm.value.remark.trim()
  };
  if (!payload.name || !payload.grade) {
    setClassesStatus("请填写班级名称和年级。", "error");
    return;
  }
  classSaving.value = true;
  try {
    if (classEditingId.value) {
      await put(`/api/admin/classes/${classEditingId.value}`, payload);
      setClassesStatus("班级信息已更新。", "success");
    } else {
      await post("/api/admin/classes", payload);
      setClassesStatus("班级已新增。", "success");
    }
    closeClassForm();
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
    openEditForm(item);
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

async function submitUserForm() {
  const account = userAccount.value.trim();
  const name = userDisplayName.value.trim();
  savingUser.value = true;
  setStatus(userFormStatus, editingUsername.value ? "正在保存用户信息…" : "正在创建用户…", "loading");
  try {
    const successMessage = editingUsername.value ? "用户信息已更新。" : "用户创建成功。";
    if (editingUsername.value) {
      await patch(`/api/admin/users/${encodeURIComponent(editingUsername.value)}`, {
        display_name: name,
        class_name: userClassName.value
      });
    } else {
      await post("/api/admin/users", {
        username: account,
        account_id: account,
        display_name: name,
        password: userPassword.value,
        class_name: userClassName.value,
        role: "user"
      });
    }
    await loadUsers();
    if (usersStatusState.value === "success") setStatus(usersStatus, successMessage, "success");
    resetUserForm();
    closeForms();
  } catch (error) {
    setStatus(userFormStatus, `操作失败：${error.message}`, "error");
  } finally {
    savingUser.value = false;
  }
}

function parseCsv(text) {
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
    } else if (character === ",") {
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

async function importStudents(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  importingStudents.value = true;
  let imported = 0;
  const failures = [];
  try {
    const rows = parseCsv(await file.text());
    if (rows.length < 2) throw new Error("模板中没有可导入的学生记录");
    const headers = rows[0].map((header) => header.trim());
    const requiredHeaders = ["学号", "姓名", "所属班级", "初始密码"];
    const indexes = requiredHeaders.map((header) => headers.indexOf(header));
    if (indexes.some((index) => index < 0)) throw new Error("表头必须包含：学号、姓名、所属班级、初始密码");

    for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
      const values = indexes.map((index) => (rows[rowIndex][index] || "").trim());
      const [account, name, className, password] = values;
      if (!values.some(Boolean)) continue;
      if (!/^\d+$/.test(account) || !name || password.length < 8) {
        failures.push(`第 ${rowIndex + 1} 行：学号须为数字、姓名不能为空、密码至少 8 位`);
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
        imported += 1;
      } catch (error) {
        failures.push(`第 ${rowIndex + 1} 行：${error.message}`);
      }
    }

    await loadUsers();
    await loadClasses();
    const summary = `导入完成：成功 ${imported} 条，失败 ${failures.length} 条。`;
    setStatus(usersStatus, `${summary}${failures.length ? ` ${failures.slice(0, 3).join("；")}` : ""}`, failures.length ? "error" : "success");
  } catch (error) {
    setStatus(usersStatus, `导入失败：${error.message}`, "error");
  } finally {
    importingStudents.value = false;
    event.target.value = "";
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
            <div class="admin-card-heading"><div><h2>快捷入口</h2><p>快速访问常用管理功能</p></div></div>
            <div class="admin-quick-grid">
              <button @click="selectSection('experiments')"><span class="quick-icon quick-violet">验</span><span><b>实验管理</b><small>维护实验内容</small></span><i>›</i></button>
              <button @click="selectSection('users')"><span class="quick-icon quick-green">学</span><span><b>学生管理</b><small>管理学生账号</small></span><i>›</i></button>
            </div>
          </section>

          <section class="admin-dashboard-card admin-recent-experiments">
            <div class="admin-card-heading"><div><h2>最近实验</h2><p>最近更新的实验内容</p></div><button class="admin-text-link" @click="selectSection('experiments')">全部实验 <span>›</span></button></div>
            <div class="admin-table-scroll"><table class="admin-dashboard-table">
              <thead><tr><th>实验名称</th><th>学时</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-if="!recentExperiments.length"><td colspan="3" class="admin-empty">暂无实验内容</td></tr>
                <tr v-for="experiment in recentExperiments" :key="experiment.name"><td class="table-primary">{{ experiment.name }}</td><td>{{ experiment.hours }} 学时</td><td><button class="admin-row-action" @click="selectSection('experiments')">编辑</button></td></tr>
              </tbody>
            </table></div>
          </section>

          <section class="admin-dashboard-card admin-record-card">
            <div class="admin-card-heading"><div><h2>最近实验记录</h2><p>学生近期实验运行状态</p></div></div>
            <div class="admin-table-scroll"><table class="admin-dashboard-table">
              <thead><tr><th>实验</th><th>学员</th><th>状态</th><th>时间</th></tr></thead>
              <tbody>
                <tr v-if="!recentRecords.length"><td colspan="4" class="admin-empty">暂无实验记录</td></tr>
                <tr v-for="record in recentRecords" :key="`${record.experiment}-${record.time}`"><td class="table-primary">{{ record.experiment }}</td><td>{{ record.student }}</td><td><span :class="['admin-state-tag', record.status === '运行中' ? 'state-running' : 'state-missing']"><i></i>{{ record.status }}</span></td><td>{{ record.time }}</td></tr>
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
                <button type="button" :class="['student-class-item', { active: !selectedClassName }]" :aria-pressed="!selectedClassName" @click="selectedClassName = ''"><span>全部班级</span><b>{{ users.length }}</b></button>
                <button v-for="item in filteredClasses" :key="item.id" type="button" :class="['student-class-item', { active: selectedClassName === item.name }]" :aria-pressed="selectedClassName === item.name" @click="selectedClassName = item.name"><span>{{ item.name }}</span><b>{{ classStudentCount(item.name) }}</b></button>
                <p v-if="!filteredClasses.length" class="student-class-empty">暂无匹配班级</p>
              </nav>
            </aside>

            <div class="student-management-content">
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
                    <button class="btn btn-primary student-add-button" id="showCreateUser" type="button" @click="openCreateForm">＋ 新增学生</button>
                    <button class="btn btn-outline student-tool-text" type="button" @click="downloadImportTemplate">导入模板下载</button>
                    <button class="btn btn-outline student-tool-text" type="button" :disabled="importingStudents" @click="studentImportInput?.click()">{{ importingStudents ? "导入中…" : "导入学生" }}</button>
                    <button class="btn btn-outline student-tool-text" type="button" @click="exportStudents">导出学生信息</button>
                    <button class="class-tool-button" type="button" aria-label="刷新学生列表" title="刷新" @click="loadUsers">↻</button>
                    <div class="class-column-control">
                      <button class="class-tool-button" type="button" aria-label="列设置" title="列设置" :aria-expanded="showStudentColumnSettings" @click="showStudentColumnSettings = !showStudentColumnSettings">▤</button>
                      <div v-if="showStudentColumnSettings" class="class-column-menu">
                        <label v-for="column in studentColumns" :key="column.key"><input v-model="column.visible" type="checkbox">{{ column.label }}</label>
                      </div>
                    </div>
                    <button class="class-tool-button" type="button" aria-label="切换紧凑行距" title="紧凑行距" :aria-pressed="compactStudentTable" @click="compactStudentTable = !compactStudentTable">⚙</button>
                    <input ref="studentImportInput" class="hidden" type="file" accept=".csv,text/csv" aria-hidden="true" tabindex="-1" @change="importStudents">
                  </div>
                </div>

                <div class="student-table-scroll">
                  <table class="student-list-table" :class="{ 'student-table-compact': compactStudentTable }">
                    <thead><tr><th>序号</th><th v-for="column in visibleStudentColumns" :key="column.key">{{ column.label }}</th><th>操作</th></tr></thead>
                    <tbody>
                      <tr v-if="usersStatusState === 'loading'"><td :colspan="visibleStudentColumns.length + 2" class="admin-empty">正在加载学生列表…</td></tr>
                      <tr v-else-if="!filteredUsers.length"><td :colspan="visibleStudentColumns.length + 2" class="admin-empty">{{ emptyText }}</td></tr>
                      <template v-else>
                        <tr v-for="(item, index) in filteredUsers" :key="item.username">
                          <td>{{ index + 1 }}</td>
                          <td v-for="column in visibleStudentColumns" :key="column.key" :class="{ 'student-name-cell': column.key === 'display_name' }">{{ studentCellValue(item, column.key) }}</td>
                          <td class="student-row-actions">
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
              <div class="field"><label for="userClassName">所属班级</label><select id="userClassName" v-model="userClassName" class="select"><option value="">未分班</option><option v-for="item in studentClassList" :key="item.id" :value="item.name">{{ item.name }}（{{ item.grade || "年级未维护" }}）</option></select></div>
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
        </template>

        <template v-else-if="adminSection === 'classes'">
          <header class="admin-page-heading class-page-heading">
            <div><p class="admin-eyebrow">BASIC INFORMATION</p><h1>班级管理</h1><p>维护班级基础资料、年级、人数和显示顺序。</p></div>
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
                <thead><tr><th v-for="column in visibleClassColumns" :key="column.key">{{ column.label }}</th><th>操作</th></tr></thead>
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
                  <label>人数<input v-model.number="classForm.student_count" type="number" min="0" step="1" required></label>
                  <label>排序<input v-model.number="classForm.sort_order" type="number" min="0" step="1" required></label>
                  <label class="class-form-remark">备注<textarea v-model="classForm.remark" maxlength="500" rows="3" placeholder="可填写班级说明"></textarea></label>
                </div>
                <footer><button type="button" class="btn btn-outline" @click="closeClassForm">取消</button><button type="submit" class="btn btn-primary" :disabled="classSaving">{{ classSaving ? "保存中…" : "保存班级" }}</button></footer>
              </form>
            </section>
          </div>
        </template>

        <template v-else-if="adminSection === 'roles'">
          <header class="admin-page-heading">
            <div><p class="admin-eyebrow">BASIC INFORMATION</p><h1>角色管理</h1><p>查看系统内置角色及其账号数量。</p></div>
            <button class="btn btn-outline" type="button" aria-label="刷新角色信息" :disabled="loadingRoles" @click="loadRoles">{{ loadingRoles ? "刷新中…" : "刷新" }}</button>
          </header>
          <p :class="rolesStatusClass" role="status" aria-live="polite">{{ rolesStatus }}</p>
          <section class="admin-role-grid" aria-label="系统角色">
            <article v-for="role in systemRoles" :key="role.role" class="admin-dashboard-card admin-role-card">
              <div class="admin-role-card-heading">
                <span class="admin-role-icon">{{ role.role === "admin" ? "管" : "学" }}</span>
                <span class="admin-role-type">系统内置</span>
              </div>
              <h2>{{ role.name }}</h2>
              <p>{{ role.description }}</p>
              <div class="admin-role-count">
                <span>当前账号</span>
                <strong>{{ hasRolesData ? roleCounts[role.role] : "—" }}</strong>
              </div>
            </article>
          </section>
          <p class="admin-role-note">当前角色为系统内置角色，角色新增与权限配置暂未接入。</p>
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
              <button class="btn btn-outline" type="button" @click="resetExperimentSearch">重置</button>
              <button class="btn btn-primary" type="submit" :disabled="experimentLoading">查询</button>
            </form>
          </section>

          <p :class="['status', experimentStatusState]" role="status" aria-live="polite">{{ experimentStatus }}</p>

          <section class="admin-dashboard-card experiment-list-card" aria-labelledby="experimentListTitle">
            <div class="experiment-list-heading">
              <h2 id="experimentListTitle">实验列表</h2>
              <span>当前筛选 {{ experiments.length }} 条</span>
            </div>
            <div class="admin-table-scroll experiment-table-scroll">
              <table class="admin-dashboard-table experiment-table">
                <thead><tr><th>实验名称</th><th>实验时长</th><th>车辆速度</th><th>加速度</th><th>油门</th><th>车辆朝向</th><th>前视流帧率</th><th>创建时间</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-if="experimentLoading"><td colspan="9" class="admin-empty">正在读取数据库记录…</td></tr>
                  <tr v-else-if="!visibleExperiments.length"><td colspan="9" class="admin-empty">{{ experimentKeyword ? "没有匹配的实验记录" : "数据库中暂无实验记录" }}</td></tr>
                  <tr v-for="item in visibleExperiments" :key="item.id">
                    <td class="experiment-name-cell"><strong>{{ item.name }}</strong><span :class="['experiment-state', item.is_active ? 'is-active' : 'is-inactive']">{{ item.is_active ? "已启用" : "已停用" }}</span></td>
                    <td>{{ formatDuration(item.duration_seconds) }}</td>
                    <td>{{ Number(item.speed || 0).toFixed(1) }} <small>km/h</small></td>
                    <td>{{ Number(item.acceleration || 0).toFixed(2) }} <small>m/s²</small></td>
                    <td>{{ Number(item.throttle || 0).toFixed(1) }}<small>%</small></td>
                    <td>{{ Number(item.yaw || 0).toFixed(1) }}<small>°</small></td>
                    <td>{{ Number(item.front_fps || 0).toFixed(1) }} <small>fps</small></td>
                    <td>{{ formatExperimentDate(item.created_at) }}</td>
                    <td class="experiment-actions">
                      <button type="button" class="experiment-icon-action" :aria-label="`查看 ${item.name}`" title="查看" @click="experimentToView = item">◉</button>
                      <button v-if="!item.is_active" type="button" class="experiment-icon-action action-start" :aria-label="`启动 ${item.name}`" title="启动" :disabled="experimentActionId === item.id" @click="toggleExperiment(item)">▶</button>
                      <button v-else type="button" class="experiment-icon-action action-stop" :aria-label="`停用 ${item.name}`" title="停用" :disabled="experimentActionId === item.id" @click="toggleExperiment(item)">■</button>
                      <button type="button" class="experiment-icon-action" :aria-label="`编辑 ${item.name}`" title="编辑" @click="openExperimentForm(item)">✎</button>
                      <button type="button" class="experiment-icon-action action-delete" :aria-label="`删除 ${item.name}`" title="删除" :disabled="experimentActionId === item.id" @click="deleteExperiment(item)">×</button>
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
                  <label>实验时长（秒）<input v-model.number="experimentForm.duration_seconds" type="number" min="0" step="1" required></label>
                  <label>车辆速度（km/h）<input v-model.number="experimentForm.speed" type="number" step="0.1" required></label>
                  <label>加速度（m/s²）<input v-model.number="experimentForm.acceleration" type="number" step="0.01" required></label>
                  <label>油门（%）<input v-model.number="experimentForm.throttle" type="number" step="0.1" required></label>
                  <label>车辆朝向（°）<input v-model.number="experimentForm.yaw" type="number" step="0.1" required></label>
                  <label>前视流帧率（fps）<input v-model.number="experimentForm.front_fps" type="number" min="0" step="0.1" required></label>
                </div>
                <footer><button type="button" class="btn btn-outline" @click="closeExperimentForm">取消</button><button type="submit" class="btn btn-primary" :disabled="experimentSaving">{{ experimentSaving ? "保存中…" : "保存实验" }}</button></footer>
              </form>
            </section>
          </div>

          <div v-if="experimentToView" class="experiment-modal-backdrop" @click.self="experimentToView = null">
            <section class="experiment-modal experiment-detail-modal" role="dialog" aria-modal="true" aria-labelledby="experimentDetailTitle">
              <header><div><p class="admin-eyebrow">EXPERIMENT DETAIL</p><h2 id="experimentDetailTitle">{{ experimentToView.name }}</h2></div><button type="button" class="experiment-modal-close" aria-label="关闭" @click="experimentToView = null">×</button></header>
              <dl class="experiment-detail-grid">
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
