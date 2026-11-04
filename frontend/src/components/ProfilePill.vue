<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.js";

const props = defineProps({
  variant: { type: String, default: "page" }, // dashboard | page
  current: { type: Boolean, default: false }
});

const auth = useAuthStore();
const router = useRouter();

const loggingOut = ref(false);
const logoutStatus = ref("");
const logoutStatusState = ref("");

const logoutStatusClass = computed(() =>
  logoutStatusState.value ? `status logout-status ${logoutStatusState.value}` : "status logout-status"
);

const isDashboard = computed(() => props.variant === "dashboard");

function goProfile(event) {
  event.preventDefault();
  router.push("/profile");
}

async function handleLogout(event) {
  event.preventDefault();
  event.stopPropagation();
  loggingOut.value = true;
  logoutStatus.value = "正在退出…";
  logoutStatusState.value = "loading";
  try {
    await auth.logout();
    await router.push("/home");
  } catch (error) {
    logoutStatus.value = `退出登录失败：${error.message}`;
    logoutStatusState.value = "error";
  } finally {
    loggingOut.value = false;
  }
}
</script>

<template>
  <a
    class="profile-pill"
    :id="isDashboard ? 'dashboardProfileLink' : null"
    href="#profile"
    data-route="profile"
    aria-label="个人中心"
    :aria-current="current ? 'page' : null"
    @click="goProfile"
  >
    <div
      class="avatar"
      :id="isDashboard ? 'dashboardAvatar' : null"
      :data-user-avatar="isDashboard ? null : ''"
      aria-hidden="true"
    >
      <img v-if="auth.avatarUrl" class="profile-avatar-image" :src="auth.avatarUrl" alt="">
      <span v-else>{{ auth.avatarText }}</span>
    </div>
    <span class="profile-tooltip" role="tooltip"><b
        :id="isDashboard ? 'dashboardUsername' : null"
        :data-user-name="isDashboard ? null : ''"
      >{{ auth.displayName }}</b><span>账号（学号）：<span
          :id="isDashboard ? 'dashboardAccount' : null"
          :data-user-account="isDashboard ? null : ''"
        >{{ auth.accountId }}</span></span><span
        :id="isDashboard ? 'dashboardRole' : null"
        :data-user-role="isDashboard ? null : ''"
      >{{ auth.roleName }}</span><button
        class="logout-button"
        type="button"
        data-logout
        :disabled="loggingOut"
        @click="handleLogout"
      >退出登录</button><span
        :class="logoutStatusClass"
        data-logout-status
        role="status"
        aria-live="polite"
      >{{ logoutStatus }}</span></span>
  </a>
</template>
