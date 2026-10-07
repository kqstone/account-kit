<template>
  <div class="auth-card">
    <div class="auth-header">
      <h1 class="auth-title">找回密码</h1>
      <p class="auth-desc">输入绑定的邮箱获取重置验证码并设置新密码</p>
    </div>

    <div class="outbox-hint-banner">
      <span>📬 发送验证码后，可在右侧信箱中复制使用</span>
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

    <ResetPasswordForm
      v-else
      :client="client"
      language="zh"
      @success="handleResetSuccess"
    />

    <div class="auth-footer">
      <span>想起密码了？</span>
      <router-link to="/login">返回登录</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { ResetPasswordForm } from "@kqstone/account-ui-vue"
import { client, outboxDrawerOpen } from "../api"

const successMsg = ref("")

function openDrawer() {
  outboxDrawerOpen.value = true
}

function handleResetSuccess() {
  successMsg.value = "密码已成功重置！请使用新密码重新登录。"
}
</script>
