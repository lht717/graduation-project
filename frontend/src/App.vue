<script setup>
import { RouterView } from "vue-router";
import LoginModal from "@/components/LoginModal.vue";

defineOptions({ name: "AppRoot" });
</script>

<template>
  <RouterView v-slot="{ Component }">
    <KeepAlive :include="['WorkspaceView']">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
  <LoginModal />
</template>
