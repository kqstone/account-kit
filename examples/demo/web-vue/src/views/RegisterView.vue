<template>
  <div class="auth-card" style="max-width: 480px">
    <div class="auth-header">
      <h1 class="auth-title">注册新账号</h1>
      <p class="auth-desc">创建您的演示账号，体验完整的注册与审批流程</p>
    </div>

    <div class="outbox-hint-banner">
      <span>📬 点击「发送验证码」后，可在信箱中查看</span>
      <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
        查看信箱
      </button>
    </div>

    <div v-if="successMsg" class="alert alert-success">
      <div>
        <strong>{{ successMsg }}</strong>
        <div style="margin-top: 8px">
          <router-link to="/login" class="btn btn-sm">前往登录</router-link>
        </div>
      </div>
    </div>

    <RegisterForm
      v-else
      :client="client"
      language="zh"
      @success="handleRegisterSuccess"
    />

    <div class="auth-footer">
      <span>已有账号？</span>
      <router-link to="/login">立即登录</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { RegisterForm, type AccountUser } from "@kqstone/account-ui-vue"
import { client, outboxDrawerOpen } from "../api"

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
