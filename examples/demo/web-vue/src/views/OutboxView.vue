<template>
  <div class="page-container" style="max-width: 900px; margin: 0 auto">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px">
        <div>
          <h1 class="card-title" style="margin-bottom: 4px; display: flex; align-items: center; gap: 8px">
            <span>📬</span>
            <span>站内信箱 (Demo Outbox)</span>
          </h1>
          <p class="card-subtitle" style="margin-bottom: 0">
            仅用于 Demo 演示环境。系统生成的全部邮件验证码均记录在此处，供注册、改密、换绑邮箱及 2FA 流程直接取用。
          </p>
        </div>

        <div style="display: flex; align-items: center; gap: 12px">
          <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--color-text-secondary); cursor: pointer">
            <input v-model="autoRefresh" type="checkbox" />
            <span>自动刷新 (3s)</span>
          </label>
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="outboxLoading"
            @click="refresh"
          >
            {{ outboxLoading ? '刷新中…' : '🔄 立即刷新' }}
          </button>
        </div>
      </div>

      <!-- 筛选栏 -->
      <div style="display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap">
        <input
          v-model="emailFilter"
          type="text"
          placeholder="按收件人邮箱筛选…"
          class="form-input"
          style="max-width: 260px"
        />
        <select v-model="purposeFilter" class="form-select" style="max-width: 200px">
          <option value="">全部验证码用途</option>
          <option value="register">用户注册 (register)</option>
          <option value="reset_password">重置密码 (reset_password)</option>
          <option value="change_password">修改密码 (change_password)</option>
          <option value="change_email">修改邮箱 (change_email)</option>
          <option value="login_2fa">2FA登录 (login_2fa)</option>
          <option value="disable_2fa">关闭2FA (disable_2fa)</option>
          <option value="delete_account">注销账号 (delete_account)</option>
        </select>
      </div>

      <!-- 列表内容 -->
      <div v-if="filteredItems.length === 0" style="text-align: center; padding: 60px 16px; color: var(--color-text-muted)">
        <div style="font-size: 48px; margin-bottom: 12px">📭</div>
        <p style="font-size: 16px; font-weight: 500">信箱暂无验证码记录</p>
        <p style="font-size: 13px; margin-top: 6px">
          请在注册、重置密码、修改邮箱或登录双因素验证页面发送验证码，系统发出后将立即在此呈现。
        </p>
      </div>

      <div v-else style="display: flex; flex-direction: column; gap: 12px">
        <div
          v-for="(item, idx) in filteredItems"
          :key="idx"
          class="card"
          style="padding: 16px; border-left: 4px solid var(--color-primary); box-shadow: none"
        >
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px">
            <div style="display: flex; align-items: center; gap: 10px">
              <span style="font-size: 15px; font-weight: 600; color: #111827">
                收件人: {{ item.to }}
              </span>
              <span class="badge badge-blue">
                {{ formatPurposeName(item.purpose) }}
              </span>
              <span class="badge badge-gray" style="font-size: 11px">
                {{ item.purpose }}
              </span>
            </div>
            <div style="font-size: 13px; color: var(--color-text-muted)">
              发送时间: {{ formatDateTime(item.at) }}
            </div>
          </div>

          <div style="display: flex; align-items: center; justify-content: space-between; background: #f9fafb; padding: 12px 16px; border-radius: 8px; border: 1px dashed #d1d5db">
            <div>
              <span style="font-size: 13px; color: var(--color-text-secondary); margin-right: 12px">
                验证码:
              </span>
              <span style="font-family: var(--font-mono); font-size: 24px; font-weight: 700; color: var(--color-primary); letter-spacing: 4px">
                {{ item.code }}
              </span>
            </div>

            <button
              type="button"
              class="btn btn-secondary btn-sm"
              @click="copyCode(item.code, idx)"
            >
              {{ copiedIndex === idx ? '✓ 已复制到剪贴板' : '📋 复制验证码' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue"
import {
  outboxItems,
  outboxLoading,
  fetchOutbox,
  formatPurposeName,
  formatDateTime,
} from "../api"

const autoRefresh = ref(true)
const emailFilter = ref("")
const purposeFilter = ref("")
const copiedIndex = ref<number | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const filteredItems = computed(() => {
  let list = outboxItems.value
  if (emailFilter.value.trim()) {
    const q = emailFilter.value.trim().toLowerCase()
    list = list.filter((i) => i.to.toLowerCase().includes(q))
  }
  if (purposeFilter.value) {
    list = list.filter((i) => i.purpose === purposeFilter.value)
  }
  return list
})

async function refresh() {
  try {
    await fetchOutbox()
  } catch {
    // Ignore error
  }
}

async function copyCode(code: string, idx: number) {
  try {
    await navigator.clipboard.writeText(code)
    copiedIndex.value = idx
    setTimeout(() => {
      if (copiedIndex.value === idx) copiedIndex.value = null
    }, 2000)
  } catch {
    // Ignore error
  }
}

watch(autoRefresh, (enabled) => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  if (enabled) {
    timer = setInterval(refresh, 3000)
  }
})

onMounted(() => {
  void refresh()
  if (autoRefresh.value) {
    timer = setInterval(refresh, 3000)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
