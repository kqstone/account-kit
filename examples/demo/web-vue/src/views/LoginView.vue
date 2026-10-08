<template>
  <div class="auth-card">
    <div class="auth-header">
      <h1 class="auth-title">{{ tt.loginTitle }}</h1>
      <p class="auth-desc">{{ tt.loginDesc }}</p>
    </div>

    <div class="outbox-hint-banner">
      <span>📬 {{ tt.loginHint }}</span>
      <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
        {{ tt.viewMailbox }}
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
      <router-link to="/register">{{ tt.registerLink }}</router-link>
      <span>·</span>
      <router-link to="/reset">{{ tt.forgot }}</router-link>
    </div>

    <TwoFactorLoginDialog
      v-if="showMfaDialog && mfaChallenge"
      :client="client"
      :challenge="mfaChallenge"
      :scope="mfaScope"
      :device-name="deviceName"
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
import { tt } from "../i18n"

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
