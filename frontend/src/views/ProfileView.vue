<script setup>
import { computed, nextTick, ref } from "vue";
import AppLink from "@/components/AppLink.vue";
import { post } from "@/api/client.js";
import { useAuthStore } from "@/stores/auth.js";
import AppTopbar from "@/components/AppTopbar.vue";

defineOptions({ name: "ProfileView" });

const auth = useAuthStore();

const avatarInput = ref(null);
const cropStage = ref(null);
const cropImage = ref(null);
const cropImageSrc = ref("");
const cropImageSize = ref({ width: 0, height: 0 });
const cropStageSize = ref(300);
const cropZoom = ref(1);
const cropOffset = ref({ x: 0, y: 0 });
const cropSaving = ref(false);
const avatarStatus = ref("");
const avatarStatusState = ref("");
const displayNameInput = ref(auth.user.display_name || auth.user.nickname || auth.user.username || "");
const displayNameStatus = ref("");
const displayNameStatusState = ref("");
const savingName = ref(false);

const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const passwordStatus = ref("");
const passwordStatusState = ref("");
const savingPassword = ref(false);

const roleText = computed(
  () => auth.user.role_name || (auth.user.role === "admin" ? "管理员" : "普通用户")
);

const registeredText = computed(() => {
  const registeredAt = auth.user.registered_at ? new Date(auth.user.registered_at) : null;
  return registeredAt && !Number.isNaN(registeredAt.getTime())
    ? registeredAt.toLocaleString("zh-CN")
    : "—";
});

const displayNameStatusClass = computed(() =>
  displayNameStatusState.value ? `status ${displayNameStatusState.value}` : "status"
);
const passwordStatusClass = computed(() =>
  passwordStatusState.value ? `status ${passwordStatusState.value}` : "status"
);

const avatarStatusClass = computed(() =>
  avatarStatusState.value ? `status ${avatarStatusState.value}` : "status"
);

const cropImageStyle = computed(() => {
  const { width, height } = cropImageSize.value;
  if (!width || !height) return {};
  const fitScale = Math.max(cropStageSize.value / width, cropStageSize.value / height);
  return {
    width: `${width * fitScale * cropZoom.value}px`,
    height: `${height * fitScale * cropZoom.value}px`,
    left: `calc(50% + ${cropOffset.value.x}px)`,
    top: `calc(50% + ${cropOffset.value.y}px)`
  };
});

function clampCropOffset(offset, zoom = cropZoom.value) {
  const { width, height } = cropImageSize.value;
  if (!width || !height) return { x: 0, y: 0 };
  const fitScale = Math.max(cropStageSize.value / width, cropStageSize.value / height);
  const renderedWidth = width * fitScale * zoom;
  const renderedHeight = height * fitScale * zoom;
  return {
    x: Math.max((cropStageSize.value - renderedWidth) / 2, Math.min((renderedWidth - cropStageSize.value) / 2, offset.x)),
    y: Math.max((cropStageSize.value - renderedHeight) / 2, Math.min((renderedHeight - cropStageSize.value) / 2, offset.y))
  };
}

function setCropZoom(value) {
  cropZoom.value = Number(value);
  cropOffset.value = clampCropOffset(cropOffset.value);
}

async function handleAvatarChange(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    avatarStatus.value = "请选择图片文件。";
    avatarStatusState.value = "error";
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    avatarStatus.value = "图片不能超过 2 MB。";
    avatarStatusState.value = "error";
    return;
  }
  if (cropImageSrc.value) URL.revokeObjectURL(cropImageSrc.value);
  cropImageSrc.value = URL.createObjectURL(file);
  cropImageSize.value = { width: 0, height: 0 };
  cropZoom.value = 1;
  cropOffset.value = { x: 0, y: 0 };
  await nextTick();
  cropStageSize.value = cropStage.value?.getBoundingClientRect().width || 300;
}

function onCropImageLoad(event) {
  cropImageSize.value = { width: event.target.naturalWidth, height: event.target.naturalHeight };
  cropStageSize.value = cropStage.value?.getBoundingClientRect().width || 300;
}

function onCropImageError() {
  closeCrop();
  avatarStatus.value = "图片无法读取，请选择其他图片。";
  avatarStatusState.value = "error";
}

function closeCrop() {
  if (cropSaving.value) return;
  if (cropImageSrc.value) URL.revokeObjectURL(cropImageSrc.value);
  cropImageSrc.value = "";
  cropImageSize.value = { width: 0, height: 0 };
}

function beginCropDrag(event) {
  if (!cropImageSize.value.width || cropSaving.value) return;
  event.preventDefault();
  event.currentTarget.setPointerCapture(event.pointerId);
  event.currentTarget.dataset.dragX = String(event.clientX);
  event.currentTarget.dataset.dragY = String(event.clientY);
  event.currentTarget.dataset.offsetX = String(cropOffset.value.x);
  event.currentTarget.dataset.offsetY = String(cropOffset.value.y);
}

function moveCrop(event) {
  if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
  const stage = event.currentTarget;
  cropOffset.value = clampCropOffset({
    x: Number(stage.dataset.offsetX) + event.clientX - Number(stage.dataset.dragX),
    y: Number(stage.dataset.offsetY) + event.clientY - Number(stage.dataset.dragY)
  });
}

async function confirmAvatarCrop() {
  const image = cropImage.value;
  if (!image || !cropImageSize.value.width) return;
  cropSaving.value = true;
  avatarStatus.value = "正在保存头像…";
  avatarStatusState.value = "loading";
  try {
    const { width, height } = cropImageSize.value;
    const fitScale = Math.max(cropStageSize.value / width, cropStageSize.value / height);
    const renderedScale = fitScale * cropZoom.value;
    const cropSize = cropStageSize.value / renderedScale;
    const sourceX = Math.max(0, Math.min(width - cropSize, ((width * renderedScale - cropStageSize.value) / 2 - cropOffset.value.x) / renderedScale));
    const sourceY = Math.max(0, Math.min(height - cropSize, ((height * renderedScale - cropStageSize.value) / 2 - cropOffset.value.y) / renderedScale));
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 512;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("浏览器不支持图片裁剪");
    context.drawImage(image, sourceX, sourceY, cropSize, cropSize, 0, 0, canvas.width, canvas.height);
    const croppedAvatar = await new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("头像图片生成失败"));
      }, "image/jpeg", 0.9);
    });
    await auth.saveAvatar(croppedAvatar);
    avatarStatus.value = "头像已更新，仅保存在当前浏览器。";
    avatarStatusState.value = "success";
    closeCrop();
  } catch (error) {
    avatarStatus.value = `头像更新失败：${error.message}`;
    avatarStatusState.value = "error";
  } finally {
    cropSaving.value = false;
  }
}

function removeAvatar() {
  auth.removeAvatar();
  avatarStatus.value = "已恢复默认头像。";
  avatarStatusState.value = "success";
}

function refreshCompletedExperiments() {
  window.location.reload();
}

function setDisplayNameStatus(message, state = "") {
  displayNameStatus.value = message;
  displayNameStatusState.value = state;
}

function setPasswordStatus(message, state = "") {
  passwordStatus.value = message;
  passwordStatusState.value = state;
}

async function saveDisplayName() {
  const name = displayNameInput.value.trim();
  if (!name) {
    setDisplayNameStatus("自定义名称不能为空。", "error");
    return;
  }
  if (name === (auth.user.display_name || auth.user.nickname || auth.user.username)) {
    setDisplayNameStatus("自定义名称未修改。");
    return;
  }
  savingName.value = true;
  setDisplayNameStatus("正在保存自定义名称…", "loading");
  try {
    const result = await post("/api/users/me/display-name", { display_name: name });
    auth.user.display_name = result.user?.display_name || result.display_name || name;
    displayNameInput.value = auth.user.display_name;
    setDisplayNameStatus(result.message || "自定义名称修改成功。", "success");
  } catch (error) {
    setDisplayNameStatus(`自定义名称修改失败：${error.message}`, "error");
  } finally {
    savingName.value = false;
  }
}

async function changePassword() {
  if (newPassword.value !== confirmPassword.value) {
    setPasswordStatus("两次输入的新密码不一致。", "error");
    return;
  }
  savingPassword.value = true;
  setPasswordStatus("正在提交密码修改…", "loading");
  try {
    const result = await post("/api/users/me/password", {
      current_password: currentPassword.value,
      new_password: newPassword.value
    });
    currentPassword.value = "";
    newPassword.value = "";
    confirmPassword.value = "";
    setPasswordStatus(result.message || "密码修改成功。", "success");
  } catch (error) {
    setPasswordStatus(`密码修改失败：${error.message}`, "error");
  } finally {
    savingPassword.value = false;
  }
}
</script>

<template>
  <section id="profileView">
    <AppTopbar variant="page" active="profile" />
    <main class="container view-container">
      <header class="page-head"><p class="eyebrow">ACCOUNT</p><h1>个人中心</h1><p>查看账号信息并管理自己的密码。</p></header>
      <div class="profile-summary-grid">
        <section class="profile-summary-card">
          <header class="profile-summary-heading">
            <h2>我的实验</h2>
            <button class="profile-refresh" type="button" aria-label="刷新已完成实验" title="刷新" @click="refreshCompletedExperiments">
              <span aria-hidden="true">↻</span>
              <span>刷新</span>
            </button>
          </header>
          <p class="profile-empty-experiments">还没有完成的实验，<AppLink route="dashboard">去实验中心看看吧</AppLink></p>
        </section>
        <section class="profile-summary-card">
          <header class="profile-summary-heading"><h2>实验概览</h2></header>
          <div class="profile-stat-grid">
            <div class="profile-stat">
              <span>在学课程</span>
              <strong>0</strong>
            </div>
            <div class="profile-stat">
              <span>关联实验</span>
              <strong>0</strong>
            </div>
            <div class="profile-stat">
              <span>实验总时长</span>
              <strong>00:00</strong>
            </div>
          </div>
        </section>
      </div>
      <div class="account-grid">
        <section class="account-card">
          <h2>账号信息</h2>
          <div class="profile-avatar-editor">
            <div class="profile-avatar-preview" aria-hidden="true">
              <img v-if="auth.avatarUrl" :src="auth.avatarUrl" alt="">
              <span v-else>{{ auth.avatarText }}</span>
            </div>
            <div class="profile-avatar-details">
              <b>个人头像</b>
              <span>支持常见图片格式，文件大小不超过 2 MB；头像仅保存在当前浏览器。</span>
              <div class="profile-avatar-actions">
                <input
                  id="profileAvatarInput"
                  ref="avatarInput"
                  class="sr-only"
                  type="file"
                  accept="image/*"
                  aria-label="选择头像图片"
                  @change="handleAvatarChange"
                >
                <button class="btn btn-primary" type="button" @click="avatarInput?.click()">更换头像</button>
                <button class="btn btn-outline" type="button" :disabled="!auth.avatarUrl" @click="removeAvatar">恢复默认</button>
              </div>
              <p :class="avatarStatusClass" role="status" aria-live="polite">{{ avatarStatus }}</p>
            </div>
          </div>
          <dl class="account-info">
            <div><dt>账号（学号）</dt><dd data-account="accountId">{{ auth.accountId }}</dd></div>
            <div><dt>自定义名称</dt><dd>
              <form id="displayNameForm" class="account-edit-form" @submit.prevent="saveDisplayName">
                <div class="account-edit-controls">
                  <div class="field"><input id="displayName" v-model="displayNameInput" type="text" autocomplete="nickname" required maxlength="40" aria-label="自定义名称"></div>
                  <button class="btn btn-primary" type="submit" :disabled="savingName">保存名称</button>
                </div>
                <p :class="displayNameStatusClass" id="displayNameStatus" role="status" aria-live="polite">{{ displayNameStatus }}</p>
              </form>
            </dd></div>
            <div><dt>角色</dt><dd data-account="role">{{ roleText }}</dd></div>
            <div><dt>注册时间</dt><dd data-account="registered">{{ registeredText }}</dd></div>
          </dl>
        </section>
        <section class="account-card">
          <h2>修改我的密码</h2>
          <p class="view-description">此操作只修改当前登录账号的密码。</p>
          <form id="changePasswordForm" @submit.prevent="changePassword">
            <div class="field"><label for="currentPassword">当前密码</label><input id="currentPassword" v-model="currentPassword" type="password" autocomplete="current-password" required></div>
            <div class="field"><label for="newPassword">新密码</label><input id="newPassword" v-model="newPassword" type="password" minlength="8" autocomplete="new-password" required></div>
            <div class="field"><label for="confirmPassword">确认新密码</label><input id="confirmPassword" v-model="confirmPassword" type="password" minlength="8" autocomplete="new-password" required></div>
            <button class="btn btn-primary" type="submit" :disabled="savingPassword">更新密码</button>
            <p :class="passwordStatusClass" id="passwordStatus" role="status" aria-live="polite">{{ passwordStatus }}</p>
          </form>
        </section>
      </div>
    </main>
    <div v-if="cropImageSrc" class="avatar-crop-backdrop" @click.self="closeCrop">
      <section class="avatar-crop-dialog" role="dialog" aria-modal="true" aria-labelledby="avatarCropTitle">
        <header class="avatar-crop-header">
          <div><h2 id="avatarCropTitle">裁剪头像</h2><p>拖动图片调整位置，使用滑块调整缩放。</p></div>
          <button class="avatar-crop-close" type="button" aria-label="取消裁剪" @click="closeCrop">×</button>
        </header>
        <div
          ref="cropStage"
          class="avatar-crop-stage"
          :class="{ 'is-ready': cropImageSize.width }"
          aria-label="圆形头像裁剪区域，可拖动图片"
          @pointerdown="beginCropDrag"
          @pointermove="moveCrop"
        >
          <img
            ref="cropImage"
            :src="cropImageSrc"
            :style="cropImageStyle"
            alt="待裁剪头像"
            draggable="false"
            @load="onCropImageLoad"
            @error="onCropImageError"
          >
        </div>
        <label class="avatar-crop-zoom" for="avatarCropZoom">
          <span>缩放</span>
          <input id="avatarCropZoom" type="range" min="1" max="3.5" step="0.05" :value="cropZoom" @input="setCropZoom($event.target.value)">
          <output>{{ cropZoom.toFixed(2) }}×</output>
        </label>
        <p class="avatar-crop-tip">头像将以圆形显示，裁剪结果为 512 × 512 像素。</p>
        <footer class="avatar-crop-actions">
          <button class="btn btn-outline" type="button" :disabled="cropSaving" @click="closeCrop">取消</button>
          <button class="btn btn-primary" type="button" :disabled="!cropImageSize.width || cropSaving" @click="confirmAvatarCrop">
            {{ cropSaving ? "保存中…" : "确认裁剪" }}
          </button>
        </footer>
      </section>
    </div>
  </section>
</template>
