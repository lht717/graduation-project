<script setup>
import { computed } from "vue";
import AppLink from "@/components/AppLink.vue";
import ProfilePill from "@/components/ProfilePill.vue";
import { useAuthStore } from "@/stores/auth.js";

const props = defineProps({
  variant: { type: String, default: "page" }, // dashboard | page
  active: { type: String, default: "" }
});

const auth = useAuthStore();

const liveMessageLabel = computed(() => {
  if (auth.unreadTick === 0) return null;
  return auth.hasUnread ? "私信，有未读消息" : "私信";
});

const liveUnread = computed(() => auth.unreadTick > 0 && auth.hasUnread);
</script>

<template>
  <header class="topbar app-topbar">
    <AppLink class="brand" route="home" aria-label="FusionLab 首页"><div class="brand-mark" aria-hidden="true"></div>Fusion<span>Lab</span></AppLink>
    <nav class="nav app-nav" aria-label="主导航">
      <AppLink :class="{ 'app-nav-active': active === 'home' }" route="home" :aria-current="active === 'home' ? 'page' : null">首页</AppLink>
      <AppLink :class="{ 'app-nav-active': active === 'dashboard' }" route="dashboard" :aria-current="active === 'dashboard' ? 'page' : null">实验中心</AppLink>
      <AppLink :class="{ 'app-nav-active': active === 'profile' }" route="profile" :aria-current="active === 'profile' ? 'page' : null">个人中心</AppLink>
      <AppLink
        route="message"
        :class="{ 'app-nav-active': active === 'message', 'has-unread': liveUnread }"
        :aria-current="active === 'message' ? 'page' : null"
        :aria-label="liveMessageLabel"
      >私信</AppLink>
      <AppLink
        v-if="auth.isAdmin"
        :class="{ 'app-nav-active': active === 'admin' }"
        route="admin"
        :aria-current="active === 'admin' ? 'page' : null"
      >管理员后台</AppLink>
    </nav>
    <div class="app-topbar-user">
      <slot v-if="variant === 'workspace'" name="connection" />
      <ProfilePill :variant="variant" :current="active === 'profile'" />
    </div>
  </header>
</template>
