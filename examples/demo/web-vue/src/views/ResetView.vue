<template>
  <div class="auth-card">
    <div class="auth-header">
      <h1 class="auth-title">{{ tt.resetTitle }}</h1>
      <p class="auth-desc">{{ tt.resetDesc }}</p>
    </div>

    <div class="outbox-hint-banner">
      <span>📬 {{ tt.resetHint }}</span>
      <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
        {{ tt.viewMailbox }}
      </button>
    </div>

    <div v-if="isResetSuccess" class="alert alert-success">
      <div>
        <strong>{{ tt.resetOk }}</strong>
        <div style="margin-top: 8px">
          <router-link to="/login" class="btn btn-sm">{{ tt.goLoginBtn }}</router-link>
        </div>
      </div>
    </div>

    <ResetPasswordForm
      v-else
      :client="client"
      @success="handleResetSuccess"
    />

    <div class="auth-footer">
      <span>{{ tt.rememberPassword }}</span>
      <router-link to="/login">{{ tt.backLogin }}</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { ResetPasswordForm } from "@kqstone/account-ui-vue"
import { client, outboxDrawerOpen } from "../api"
import { tt } from "../i18n"

const isResetSuccess = ref(false)

function openDrawer() {
  outboxDrawerOpen.value = true
}

function handleResetSuccess() {
  isResetSuccess.value = true
}
</script>
