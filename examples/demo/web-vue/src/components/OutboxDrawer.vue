<template>
  <div v-if="outboxDrawerOpen" class="drawer-overlay" @click.self="closeDrawer">
    <div class="drawer">
      <div class="drawer-header">
        <div class="drawer-title">
          <span>{{ tt.outboxTitle }}</span>
          <span class="badge badge-gray" style="font-weight: normal">
            {{ filteredItems.length }} {{ tt.mailboxItems }}
          </span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px">
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            :disabled="outboxLoading"
            @click="refresh"
          >
            {{ outboxLoading ? tt.refreshing : tt.refresh }}
          </button>
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            style="padding: 2px 8px; font-size: 16px"
            @click="closeDrawer"
          >
            ✕
          </button>
        </div>
      </div>

      <div style="padding: 10px 20px; background: #fafafa; border-bottom: 1px solid var(--color-border); display: flex; align-items: center; justify-content: space-between; gap: 12px">
        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--color-text-secondary); cursor: pointer">
          <input v-model="autoRefresh" type="checkbox" />
          <span>{{ tt.autoRefresh }}</span>
        </label>
        <input
          v-model="search"
          type="text"
          :placeholder="tt.searchMailbox"
          class="form-input"
          style="padding: 4px 8px; font-size: 12px; width: 160px"
        />
      </div>

      <div class="drawer-body">
        <div v-if="filteredItems.length === 0" style="text-align: center; padding: 40px 16px; color: var(--color-text-muted)">
          <div style="font-size: 32px; margin-bottom: 8px">📭</div>
          <p style="font-size: 14px">{{ tt.outboxEmptyDrawerVue }}</p>
          <p style="font-size: 12px; margin-top: 4px">{{ tt.outboxEmptySub }}</p>
        </div>

        <div v-for="(item, idx) in filteredItems" :key="idx" class="outbox-item">
          <div class="outbox-item-head">
            <span class="outbox-item-to">{{ item.to }}</span>
            <span class="badge badge-blue">{{ formatPurposeName(item.purpose) }}</span>
          </div>

          <div class="outbox-item-code-row">
            <div>
              <span style="font-size: 12px; color: var(--color-text-muted); margin-right: 8px">{{ tt.codeLabel }}:</span>
              <span class="outbox-item-code">{{ item.code }}</span>
            </div>
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              @click="copyCode(item.code, idx)"
            >
              {{ copiedIndex === idx ? tt.copiedCheck : tt.copyBtn }}
            </button>
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center">
            <span class="outbox-item-time">{{ formatDateTime(item.at) }}</span>
            <span style="font-size: 11px; color: #9ca3af">{{ item.language }}</span>
          </div>
        </div>
      </div>

      <div class="drawer-footer">
        <span>{{ tt.consoleMailActive }}</span>
        <router-link to="/outbox" style="font-size: 13px" @click="closeDrawer">{{ tt.goToOutboxPage }}</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue"
import {
  outboxDrawerOpen,
  outboxItems,
  outboxLoading,
  fetchOutbox,
  formatPurposeName,
  formatDateTime,
} from "../api"
import { tt } from "../i18n"

const autoRefresh = ref(true)
const search = ref("")
const copiedIndex = ref<number | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return outboxItems.value
  return outboxItems.value.filter(
    (item) =>
      item.to.toLowerCase().includes(q) ||
      item.purpose.toLowerCase().includes(q) ||
      formatPurposeName(item.purpose).toLowerCase().includes(q) ||
      item.code.includes(q),
  )
})

function closeDrawer() {
  outboxDrawerOpen.value = false
}

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
    // Fallback or ignore
  }
}

watch(autoRefresh, (enabled) => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  if (enabled && outboxDrawerOpen.value) {
    timer = setInterval(refresh, 3000)
  }
})

watch(outboxDrawerOpen, (open) => {
  if (open) {
    refresh()
    if (autoRefresh.value && !timer) {
      timer = setInterval(refresh, 3000)
    }
  } else {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }
})

onMounted(() => {
  if (outboxDrawerOpen.value) {
    refresh()
    if (autoRefresh.value) {
      timer = setInterval(refresh, 3000)
    }
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
