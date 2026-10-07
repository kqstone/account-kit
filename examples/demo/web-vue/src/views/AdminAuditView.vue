<template>
  <div class="page-container">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px">
        <div>
          <h1 class="card-title" style="margin-bottom: 4px">审计日志</h1>
          <p class="card-subtitle" style="margin-bottom: 0">
            查询系统安全审计日志，包含登录、改密、2FA、令牌刷新与管理员变更等详细记录。
          </p>
        </div>
        <div style="display: flex; gap: 10px">
          <router-link to="/admin" class="btn btn-secondary">
            👥 返回用户管理
          </router-link>
          <button type="button" class="btn btn-secondary" :disabled="loading" @click="loadLogs">
            {{ loading ? '加载中…' : '🔄 刷新日志' }}
          </button>
        </div>
      </div>

      <div v-if="error" class="alert alert-error">
        {{ error }}
      </div>

      <!-- 筛选栏 -->
      <div style="display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center">
        <div style="flex: 1; min-width: 200px">
          <select v-model="filterEvent" class="form-select" @change="onFilterChange">
            <option value="">全部事件类型 (All Events)</option>
            <option v-for="ev in eventOptions" :key="ev.value" :value="ev.value">
              {{ ev.label }} ({{ ev.value }})
            </option>
          </select>
        </div>

        <div style="width: 160px">
          <input
            v-model="filterIp"
            type="text"
            placeholder="按 IP 过滤…"
            class="form-input"
            @keyup.enter="onFilterChange"
          />
        </div>

        <div style="width: 200px">
          <input
            v-model="filterUserId"
            type="text"
            placeholder="按用户 ID 过滤…"
            class="form-input"
            @keyup.enter="onFilterChange"
          />
        </div>

        <button type="button" class="btn btn-primary" :disabled="loading" @click="onFilterChange">
          查询
        </button>
      </div>

      <!-- 日志表格 -->
      <div class="table-container">
        <table class="table">
          <thead>
            <tr>
              <th style="width: 180px">记录时间</th>
              <th style="width: 160px">事件</th>
              <th style="width: 150px">用户 ID</th>
              <th style="width: 130px">客户端 IP</th>
              <th style="width: 140px">设备信息</th>
              <th>元数据详情 (Meta)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && items.length === 0">
              <td colspan="6" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                正在加载审计日志…
              </td>
            </tr>
            <tr v-else-if="items.length === 0">
              <td colspan="6" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                暂无符合条件的审计日志
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

      <!-- 分页控制 -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 16px; flex-wrap: wrap; gap: 10px">
        <div style="font-size: 13px; color: var(--color-text-secondary)">
          共 <strong>{{ total }}</strong> 条记录，当前第 {{ page }} / {{ totalPages }} 页
        </div>

        <div style="display: flex; gap: 8px; align-items: center">
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            :disabled="page <= 1 || loading"
            @click="goToPage(page - 1)"
          >
            上一页
          </button>
          <span style="font-size: 13px; padding: 0 4px">
            第 {{ page }} 页
          </span>
          <button
            type="button"
            class="btn btn-secondary btn-sm"
            :disabled="page >= totalPages || loading"
            @click="goToPage(page + 1)"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { getAdminAuditLogs, formatDateTime, type AuditLogItem } from "../api"

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

const eventOptions = [
  { value: "login_success", label: "登录成功" },
  { value: "login_failed", label: "登录失败" },
  { value: "login_2fa_failed", label: "2FA 验证失败" },
  { value: "2fa_enabled", label: "开启 2FA" },
  { value: "2fa_disabled", label: "关闭 2FA" },
  { value: "2fa_reset", label: "重置 2FA" },
  { value: "2fa_recovery_regenerated", label: "重新生成恢复码" },
  { value: "password_changed", label: "修改密码" },
  { value: "password_reset", label: "重置密码" },
  { value: "email_changed", label: "修改邮箱" },
  { value: "logout", label: "退出登录" },
  { value: "refresh_reuse_detected", label: "刷新令牌重用检测" },
  { value: "account_deleted", label: "账号注销" },
  { value: "verification_code_locked", label: "验证码锁定" },
  { value: "admin_user_updated", label: "管理员更新用户" },
  { value: "admin_user_deleted", label: "管理员删除用户" },
  { value: "admin_role_changed", label: "角色变更" },
  { value: "admin_tier_changed", label: "等级变更" },
  { value: "role_change_reviewed", label: "角色申请审核" },
]

function eventLabel(ev: string): string {
  const found = eventOptions.find((o) => o.value === ev)
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
    error.value = err.message || "加载审计日志失败"
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
