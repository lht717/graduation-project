<script setup>
import { RouterView, useRoute } from "vue-router";
import LoginModal from "@/components/LoginModal.vue";
import AppTopbar from "@/components/AppTopbar.vue";

defineOptions({ name: "AppRoot" });

const route = useRoute();
</script>

<template>
  <AppTopbar v-if="route.name !== 'admin'" />
  <RouterView v-slot="{ Component }">
    <KeepAlive :include="['WorkspaceView']">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
  <LoginModal />
</template>
