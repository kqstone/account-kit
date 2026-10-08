<template>
  <div class="auth-card" style="max-width: 480px">
    <div class="auth-header">
      <h1 class="auth-title">{{ tt.registerTitle }}</h1>
      <p class="auth-desc">{{ tt.registerDesc }}</p>
    </div>

    <div class="outbox-hint-banner">
      <span>📬 {{ tt.registerHint }}</span>
      <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
        {{ tt.viewMailbox }}
      </button>
    </div>

    <div v-if="successMsg" class="alert alert-success">
      <div>
        <strong>{{ successMsg }}</strong>
        <div style="margin-top: 8px">
          <router-link to="/login" class="btn btn-sm">{{ tt.goLoginBtn }}</router-link>
        </div>
      </div>
    </div>

    <RegisterForm
      v-else
      :client="client"
      @success="handleRegisterSuccess"
    />

    <div class="auth-footer">
      <span>{{ tt.haveAccount }}</span>
      <router-link to="/login">{{ tt.goLoginNow }}</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { RegisterForm, type AccountUser } from "@kqstone/account-ui-vue"
import { client, outboxDrawerOpen } from "../api"
import { tt } from "../i18n"

const successMsg = ref("")

function openDrawer() {
  outboxDrawerOpen.value = true
}

function handleRegisterSuccess(user: AccountUser) {
  if (user.approval_status === "pending") {
    successMsg.value = `账号 ${user.username} 注册成功！由于系统开启了管理员审批，请等待管理员通过审批后再登录。`
  } else {
    successMsg.value = `账号 ${user.username} 注册成功！现在可以直接使用设置的密码登录。`
  }
}
</script>
