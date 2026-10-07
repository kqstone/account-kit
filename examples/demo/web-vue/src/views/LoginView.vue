<template>
  <div class="auth-card">
    <div class="auth-header">
      <h1 class="auth-title">登录账号</h1>
      <p class="auth-desc">输入用户名与密码登录 account-kit 演示系统</p>
    </div>

    <div class="outbox-hint-banner">
      <span>📬 如果账号开启了邮箱 2FA，请在信箱获取验证码</span>
      <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
        查看信箱
      </button>
    </div>

    <div v-if="loginError" class="alert alert-error" style="margin-bottom: 16px">
      {{ loginError }}
    </div>

    <LoginForm
      :client="client"
      :device-name="deviceName"
      :trusted-device-token="resolveTrustedDevice"
      @success="handleLoginSuccess"
      @mfa="handleMfaRequired"
    />

    <div class="auth-footer">
      <router-link to="/register">注册新账号</router-link>
      <span>·</span>
      <router-link to="/reset">忘记密码？</router-link>
    </div>

    <TwoFactorLoginDialog
      v-if="showMfaDialog && mfaChallenge"
      :client="client"
      :challenge="mfaChallenge"
      :scope="mfaScope"
      :device-name="deviceName"
      language="zh"
      @success="handleMfaSuccess"
      @cancel="showMfaDialog = false"
      @expired="handleMfaExpired"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import { useRouter, useRoute } from "vue-router"
import {
  LoginForm,
  TwoFactorLoginDialog,
  getTrustedDeviceToken,
  trustedDeviceScope,
  type LoginSecondFactorResult,
  type TokenPair,
} from "@kqstone/account-ui-vue"
import {
  client,
  tokenStore,
  refreshCurrentUser,
  outboxDrawerOpen,
} from "../api"

const router = useRouter()
const route = useRoute()

const deviceName = "Web Browser"
const loginError = ref("")
const showMfaDialog = ref(false)
const mfaChallenge = ref<any>(null)

const mfaScope = computed(() => {
  const username = mfaChallenge.value?.username || ""
  return trustedDeviceScope("", username)
})

function resolveTrustedDevice(username: string): string {
  const scope = trustedDeviceScope("", username)
  return getTrustedDeviceToken(scope)
}

function openDrawer() {
  outboxDrawerOpen.value = true
}

async function handleLoginSuccess(token: string, payload?: { tokens?: TokenPair }) {
  loginError.value = ""
  const tokens = payload?.tokens || {
    access_token: token,
    token_type: "bearer",
  }
  tokenStore.set(tokens)
  await refreshCurrentUser()
  const redirect = (route.query.redirect as string) || "/account"
  router.push(redirect)
}

function handleMfaRequired(challenge: any) {
  loginError.value = ""
  mfaChallenge.value = challenge
  showMfaDialog.value = true
}

async function handleMfaSuccess(data: LoginSecondFactorResult) {
  showMfaDialog.value = false
  const tokens: TokenPair = {
    access_token: data.access_token,
    token_type: data.token_type || "bearer",
    refresh_token: data.refresh_token,
    refresh_expires_in: data.refresh_expires_in,
  }
  tokenStore.set(tokens)
  await refreshCurrentUser()
  const redirect = (route.query.redirect as string) || "/account"
  router.push(redirect)
}

function handleMfaExpired(message: string) {
  showMfaDialog.value = false
  loginError.value = message || "两步验证挑战已过期，请重新登录"
}
</script>
