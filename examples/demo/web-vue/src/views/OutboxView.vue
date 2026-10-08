<template>
  <div class="page-container" style="max-width: 900px; margin: 0 auto">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px">
        <div>
          <h1 class="card-title" style="margin-bottom: 4px; display: flex; align-items: center; gap: 8px">
            <span>📬</span>
            <span>{{ tt.outboxPageTitleVue }}</span>
          </h1>
          <p class="card-subtitle" style="margin-bottom: 0">
            {{ tt.outboxPageDescVue }}
          </p>
        </div>

        <div style="display: flex; align-items: center; gap: 12px">
          <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--color-text-secondary); cursor: pointer">
            <input v-model="autoRefresh" type="checkbox" />
            <span>{{ tt.autoRefresh }}</span>
          </label>
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="outboxLoading"
            @click="refresh"
          >
            {{ outboxLoading ? tt.refreshing : tt.refreshBtnIcon }}
          </button>
        </div>
      </div>

      <!-- Filter bar -->
      <div style="display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap">
        <input
          v-model="emailFilter"
          type="text"
          :placeholder="tt.filterRecipientVuePlaceholder"
          class="form-input"
          style="max-width: 260px"
        />
        <select v-model="purposeFilter" class="form-select" style="max-width: 200px">
          <option value="">{{ tt.purposeOptAll }}</option>
          <option value="register">{{ tt.purposeOptRegister }}</option>
          <option value="reset_password">{{ tt.purposeOptResetPassword }}</option>
          <option value="change_password">{{ tt.purposeOptChangePassword }}</option>
          <option value="change_email">{{ tt.purposeOptChangeEmail }}</option>
          <option value="login_2fa">{{ tt.purposeOptLogin2fa }}</option>
          <option value="disable_2fa">{{ tt.purposeOptDisable2fa }}</option>
          <option value="delete_account">{{ tt.purposeOptDeleteAccount }}</option>
        </select>
      </div>

      <!-- Outbox list -->
      <div v-if="filteredItems.length === 0" style="text-align: center; padding: 60px 16px; color: var(--color-text-muted)">
        <div style="font-size: 48px; margin-bottom: 12px">📭</div>
        <p style="font-size: 16px; font-weight: 500">{{ tt.outboxEmptyDrawer }}</p>
        <p style="font-size: 13px; margin-top: 6px">
          {{ tt.outboxEmptySub }}
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
                {{ tt.recipientLabel }}: {{ item.to }}
              </span>
              <span class="badge badge-blue">
                {{ formatPurposeName(item.purpose) }}
              </span>
              <span class="badge badge-gray" style="font-size: 11px">
                {{ item.purpose }}
              </span>
            </div>
            <div style="font-size: 13px; color: var(--color-text-muted)">
              {{ tt.sentTimeLabel }}: {{ formatDateTime(item.at) }}
            </div>
          </div>

          <div style="display: flex; align-items: center; justify-content: space-between; background: #f9fafb; padding: 12px 16px; border-radius: 8px; border: 1px dashed #d1d5db">
            <div>
              <span style="font-size: 13px; color: var(--color-text-secondary); margin-right: 12px">
                {{ tt.codeLabel }}:
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
              {{ copiedIndex === idx ? tt.copiedToClipboard : tt.copyCodeIcon }}
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
import { tt } from "../i18n"

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
