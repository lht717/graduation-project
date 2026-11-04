<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.js";
import AppLink from "@/components/AppLink.vue";

const auth = useAuthStore();
const router = useRouter();

const username = ref("");
const password = ref("");
const selectedRole = ref("student");

function goHome() {
  auth.closeLogin();
  router.push("/home");
}

async function submit() {
  const ok = await auth.login(username.value, password.value, selectedRole.value);
  if (ok) router.push("/dashboard");
}
</script>

<template>
  <div id="loginModal" class="login-screen" :class="{ hidden: !auth.loginModalOpen }">
    <aside class="login-visual">
      <AppLink class="brand login-brand" route="home" aria-label="FusionLab 首页">
        <div class="brand-mark"></div>Fusion<span>Lab</span>
      </AppLink>
      <div class="login-visual-copy">
        <span class="login-visual-eyebrow">FUSIONLAB LEARNING PLATFORM</span>
        <h2>探索智能驾驶<br />开启工程实践</h2>
        <p>从仿真场景到视觉感知，在实践中连接算法与真实世界。</p>
      </div>
      <div class="login-orb login-orb-one"></div>
      <div class="login-orb login-orb-two"></div>
    </aside>

    <main class="login-panel">
      <a class="login-back" href="#home" @click.prevent="goHome">
        <span aria-hidden="true">←</span> 返回首页
      </a>

      <form class="login-form" @submit.prevent="submit">
        <h1>欢迎登录</h1>
        <p class="login-subtitle">请选择身份后进入学习平台</p>

        <div class="login-role-tabs" role="tablist" aria-label="选择登录身份">
          <button
            type="button"
            role="tab"
            :aria-selected="selectedRole === 'student'"
            :class="{ active: selectedRole === 'student' }"
            @click="selectedRole = 'student'"
          >学生</button>
          <button
            type="button"
            role="tab"
            :aria-selected="selectedRole === 'teacher'"
            :class="{ active: selectedRole === 'teacher' }"
            @click="selectedRole = 'teacher'"
          >教师</button>
        </div>

        <div class="field login-field">
          <label for="username">账号</label>
          <input
            id="username"
            v-model="username"
            autocomplete="username"
            placeholder="请输入账号"
            required
          />
        </div>
        <div class="field login-field">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
          />
        </div>

        <p id="loginStatus" role="status" :class="['status', 'login-status', auth.loginStatusState]">
          {{ auth.loginStatus }}
        </p>
        <button class="login-submit" type="submit" :disabled="auth.loginPending">进入平台</button>
        <p class="login-hint">学生请使用学号登录；教师使用管理端账号。密码与后台配置一致。</p>
      </form>
    </main>
  </div>
</template>
