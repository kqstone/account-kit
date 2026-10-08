<template>
  <div class="page-container">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px">
        <div>
          <h1 class="card-title" style="margin-bottom: 4px">{{ tt.adminAuditHeading }}</h1>
          <p class="card-subtitle" style="margin-bottom: 0">
            {{ tt.adminAuditDesc }}
          </p>
        </div>
        <div style="display: flex; gap: 10px">
          <router-link to="/admin" class="btn btn-secondary">
            {{ tt.backToUsersBtn }}
          </router-link>
          <button type="button" class="btn btn-secondary" :disabled="loading" @click="loadLogs">
            {{ loading ? tt.refreshingBtn : tt.refreshLogsBtn }}
          </button>
        </div>
      </div>

      <div v-if="error" class="alert alert-error">
        {{ error }}
      </div>

      <!-- Filter bar -->
      <div style="display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center">
        <div style="flex: 1; min-width: 200px">
          <select v-model="filterEvent" class="form-select" @change="onFilterChange">
            <option value="">{{ tt.allEventsVue }}</option>
            <option v-for="ev in eventOptions" :key="ev.value" :value="ev.value">
              {{ ev.label }} ({{ ev.value }})
            </option>
          </select>
        </div>

        <div style="width: 160px">
          <input
            v-model="filterIp"
            type="text"
            :placeholder="tt.filterIpPlaceholder"
            class="form-input"
            @keyup.enter="onFilterChange"
          />
        </div>

        <div style="width: 200px">
          <input
            v-model="filterUserId"
            type="text"
            :placeholder="tt.filterUserIdPlaceholder"
            class="form-input"
            @keyup.enter="onFilterChange"
          />
        </div>

        <button type="button" class="btn btn-primary" :disabled="loading" @click="onFilterChange">
          {{ tt.queryBtn }}
        </button>
      </div>

      <!-- Log table -->
      <div class="table-container">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 180px">{{ tt.thRecordedTime }}</th>
              <th style="width: 160px">{{ tt.thEvent }}</th>
              <th style="width: 150px">{{ tt.thUserId }}</th>
              <th style="width: 130px">{{ tt.thClientIp }}</th>
              <th style="width: 140px">{{ tt.thDeviceInfo }}</th>
              <th>{{ tt.thMetadata }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && items.length === 0">
              <td colspan="6" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                {{ tt.loadingAuditLogs }}
              </td>
            </tr>
            <tr v-else-if="items.length === 0">
              <td colspan="6" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                {{ tt.noAuditLogsFound }}
              </td>
            </tr>
            <tr v-for="item in items" :key="item.id">
              <td style="font-size: 13px; color: #4b5563">
                {{ formatDateTime(item.created_at) }}
              </td>
              <td>
                <span class="badge" :class="eventBadgeClass(item.event)">
                  {{ eventLabel(item.event) }}
                </span>
                <div style="font-size: 11px; color: var(--color-text-muted); font-family: var(--font-mono); margin-top: 2px">
                  {{ item.event }}
                </div>
              </td>
              <td style="font-size: 12px; font-family: var(--font-mono)">
                {{ item.user_id ? item.user_id.slice(0, 8) + '…' : '-' }}
              </td>
              <td style="font-size: 13px; font-family: var(--font-mono)">
                {{ item.ip || '-' }}
              </td>
              <td style="font-size: 13px">
                {{ item.device_name || '-' }}
              </td>
              <td>
                <pre style="margin: 0; font-family: var(--font-mono); font-size: 11px; max-width: 400px; max-height: 80px; overflow: auto; background: #f9fafb; padding: 4px 8px; border-radius: 4px; border: 1px solid #e5e7eb">{{ JSON.stringify(item.meta, null, 2) }}</pre>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 16px; flex-wrap: wrap; gap: 10px">
        <div style="font-size: 13px; color: var(--color-text-secondary)">
          {{ tt.totalRecordsPrefix }} <strong>{{ total }}</strong> {{ tt.recordsCountUnit }}，{{ tt.currentPagePrefix }} {{ page }} / {{ totalPages }}
        </div>

        <div style="display: flex; gap: 8px; align-items: center">
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            :disabled="page <= 1 || loading"
            @click="goToPage(page - 1)"
          >
            {{ tt.prevPageBtn }}
          </button>
          <span style="font-size: 13px; padding: 0 4px">
            {{ tt.pageNumber.replace('{page}', String(page)) }}
          </span>
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            :disabled="page >= totalPages || loading"
            @click="goToPage(page + 1)"
          >
            {{ tt.nextPageBtn }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { getAdminAuditLogs, formatDateTime, type AuditLogItem } from "../api"
import { tt } from "../i18n"

const items = ref<AuditLogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const error = ref("")

const filterEvent = ref("")
const filterIp = ref("")
const filterUserId = ref("")

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const eventOptions = computed(() => [
  { value: "login_success", label: tt.value.audit_login_success },
  { value: "login_failed", label: tt.value.audit_login_failed },
  { value: "login_2fa_failed", label: tt.value.audit_login_2fa_failed },
  { value: "2fa_enabled", label: tt.value.audit_2fa_enabled },
  { value: "2fa_disabled", label: tt.value.audit_2fa_disabled },
  { value: "2fa_reset", label: tt.value.audit_2fa_reset },
  { value: "2fa_recovery_regenerated", label: tt.value.audit_2fa_recovery_regenerated },
  { value: "password_changed", label: tt.value.audit_password_changed },
  { value: "password_reset", label: tt.value.audit_password_reset },
  { value: "email_changed", label: tt.value.audit_email_changed },
  { value: "logout", label: tt.value.audit_logout },
  { value: "refresh_reuse_detected", label: tt.value.audit_refresh_reuse_detected },
  { value: "account_deleted", label: tt.value.audit_account_deleted },
  { value: "verification_code_locked", label: tt.value.audit_verification_code_locked },
  { value: "admin_user_updated", label: tt.value.audit_admin_user_updated },
  { value: "admin_user_deleted", label: tt.value.audit_admin_user_deleted },
  { value: "admin_role_changed", label: tt.value.audit_admin_role_changed_vue },
  { value: "admin_tier_changed", label: tt.value.audit_admin_tier_changed_vue },
  { value: "role_change_reviewed", label: tt.value.audit_role_change_reviewed },
])

function eventLabel(ev: string): string {
  const found = eventOptions.value.find((o) => o.value === ev)
  return found ? found.label : ev
}

function eventBadgeClass(ev: string): string {
  if (ev.includes("failed") || ev.includes("locked") || ev.includes("reuse")) {
    return "badge-red"
  }
  if (ev.includes("success") || ev.includes("enabled") || ev.includes("changed")) {
    return "badge-green"
  }
  if (ev.includes("reset") || ev.includes("deleted") || ev.includes("disabled")) {
    return "badge-yellow"
  }
  return "badge-blue"
}

async function loadLogs() {
  error.value = ""
  loading.value = true
  try {
    const res = await getAdminAuditLogs({
      page: page.value,
      page_size: pageSize.value,
      event: filterEvent.value || undefined,
      ip: filterIp.value.trim() || undefined,
      user_id: filterUserId.value.trim() || undefined,
    })
    items.value = res.items || []
    total.value = res.total || 0
  } catch (err: any) {
    error.value = err.message || tt.value.loadAuditLogsFailed
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  void loadLogs()
}

function goToPage(p: number) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  void loadLogs()
}

onMounted(() => {
  void loadLogs()
})
</script>
