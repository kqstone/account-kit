<template>
  <div class="page-container">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px">
        <div>
          <h1 class="card-title" style="margin-bottom: 4px">{{ tt.adminUsersTitle }}</h1>
          <p class="card-subtitle" style="margin-bottom: 0">
            {{ tt.adminUsersDesc }}
          </p>
        </div>
        <div style="display: flex; gap: 10px">
          <router-link to="/admin/audit" class="btn btn-secondary">
            {{ tt.viewAuditLogsBtn }}
          </router-link>
          <button type="button" class="btn btn-secondary" :disabled="loading" @click="loadUsers">
            {{ loading ? tt.refreshingBtn : tt.refreshUsersBtn }}
          </button>
        </div>
      </div>

      <div v-if="error" class="alert alert-error">
        {{ error }}
      </div>

      <div v-if="successMsg" class="alert alert-success">
        {{ successMsg }}
      </div>

      <!-- Search and filter -->
      <div style="display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap">
        <input
          v-model="searchTerm"
          type="text"
          :placeholder="tt.searchUserPlaceholder"
          class="form-input"
          style="max-width: 260px"
        />
        <select v-model="statusFilter" class="form-select" style="max-width: 180px">
          <option value="">{{ tt.allApprovalStatuses }}</option>
          <option value="pending">{{ tt.approvalOptPending }}</option>
          <option value="approved">{{ tt.approvalOptApproved }}</option>
          <option value="rejected">{{ tt.approvalOptRejected }}</option>
        </select>
      </div>

      <!-- Users table -->
      <div class="table-container">
        <table class="table">
          <thead>
            <tr>
              <th>{{ tt.thUsernameAndName }}</th>
              <th>{{ tt.thEmail }}</th>
              <th>{{ tt.thRole }}</th>
              <th>{{ tt.thTier }}</th>
              <th>{{ tt.thApprovalStatus }}</th>
              <th>{{ tt.thAccountStatus }}</th>
              <th>{{ tt.thIsAdmin }}</th>
              <th style="text-align: right">{{ tt.thActions }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && users.length === 0">
              <td colspan="8" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                {{ tt.loadingUsersText }}
              </td>
            </tr>
            <tr v-else-if="filteredUsers.length === 0">
              <td colspan="8" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                {{ tt.noMatchingUsers }}
              </td>
            </tr>
            <tr v-for="user in filteredUsers" :key="user.id">
              <td>
                <div style="font-weight: 600">{{ user.username }}</div>
                <div v-if="user.full_name" style="font-size: 12px; color: var(--color-text-muted)">
                  {{ user.full_name }}
                </div>
              </td>
              <td>{{ user.email }}</td>
              <td>
                <span class="badge badge-gray">{{ user.role || 'user' }}</span>
              </td>
              <td>
                <span
                  class="badge"
                  :style="{ background: user.tier_badge_color || '#8c8c8c', color: '#fff' }"
                >
                  {{ user.tier_name || user.tier || tt.tierFree }}
                </span>
              </td>
              <td>
                <span v-if="user.approval_status === 'approved'" class="badge badge-green">{{ tt.statusApproved }}</span>
                <span v-else-if="user.approval_status === 'pending'" class="badge badge-yellow">{{ tt.statusPending }}</span>
                <span v-else class="badge badge-red">{{ tt.statusRejected }}</span>
              </td>
              <td>
                <span v-if="user.is_active" class="badge badge-green">{{ tt.statusActive }}</span>
                <span v-else class="badge badge-red">{{ tt.statusDeactivated }}</span>
              </td>
              <td>
                <span v-if="user.is_admin" class="badge badge-blue">{{ tt.roleAdmin }}</span>
                <span v-else style="color: var(--color-text-muted); font-size: 13px">{{ tt.noText }}</span>
              </td>
              <td style="text-align: right">
                <div style="display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap">
                  <!-- Approval actions -->
                  <template v-if="!user.is_admin && user.approval_status === 'pending'">
                    <button
                      type="button"
                      class="btn btn-sm"
                      style="background-color: #52c41a"
                      :disabled="operatingId === user.id"
                      @click="updateApproval(user, 'approved')"
                    >
                      {{ tt.btnApprove }}
                    </button>
                    <button
                      type="button"
                      class="btn btn-secondary btn-sm"
                      :disabled="operatingId === user.id"
                      @click="updateApproval(user, 'rejected')"
                    >
                      {{ tt.btnReject }}
                    </button>
                  </template>
                  <template v-else-if="!user.is_admin && user.approval_status === 'rejected'">
                    <button
                      type="button"
                      class="btn btn-sm"
                      :disabled="operatingId === user.id"
                      @click="updateApproval(user, 'approved')"
                    >
                      {{ tt.btnReApprove }}
                    </button>
                  </template>

                  <!-- Active status toggle -->
                  <button
                    v-if="!user.is_admin"
                    type="button"
                    class="btn btn-secondary btn-sm"
                    :disabled="operatingId === user.id"
                    @click="toggleActive(user)"
                  >
                    {{ user.is_active ? tt.btnDeactivate : tt.btnEnable }}
                  </button>

                  <!-- Reset 2FA -->
                  <button
                    type="button"
                    class="btn btn-secondary btn-sm"
                    :title="tt.titleReset2fa"
                    :disabled="operatingId === user.id"
                    @click="handleReset2fa(user)"
                  >
                    {{ tt.btnReset2faShort }}
                  </button>

                  <!-- Delete -->
                  <button
                    v-if="!user.is_admin"
                    type="button"
                    class="btn btn-danger-outline btn-sm"
                    :disabled="operatingId === user.id"
                    @click="handleDeleteUser(user)"
                  >
                    {{ tt.btnDelete }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import {
  getAdminUsers,
  patchAdminUser,
  resetAdminUser2fa,
  deleteAdminUser,
} from "../api"
import type { AccountUser } from "@kqstone/account-ui-vue"
import { tt } from "../i18n"

const users = ref<AccountUser[]>([])
const loading = ref(false)
const operatingId = ref<string | null>(null)
const error = ref("")
const successMsg = ref("")
const searchTerm = ref("")
const statusFilter = ref("")

const filteredUsers = computed(() => {
  let list = users.value
  if (statusFilter.value) {
    list = list.filter((u) => u.approval_status === statusFilter.value)
  }
  const q = searchTerm.value.trim().toLowerCase()
  if (q) {
    list = list.filter(
      (u) =>
        u.username.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        (u.full_name && u.full_name.toLowerCase().includes(q)),
    )
  }
  return list
})

async function loadUsers() {
  error.value = ""
  loading.value = true
  try {
    users.value = await getAdminUsers()
  } catch (err: any) {
    error.value = err.message || tt.value.loadUsersFailed
  } finally {
    loading.value = false
  }
}

async function updateApproval(user: AccountUser, status: "approved" | "rejected") {
  error.value = ""
  successMsg.value = ""
  operatingId.value = user.id
  try {
    const updated = await patchAdminUser(user.id, { approval_status: status })
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx !== -1) users.value[idx] = updated
    const statusText = status === "approved" ? tt.value.statusApproved : tt.value.statusRejected
    successMsg.value = tt.value.userApprovalUpdated.replace("{username}", user.username).replace("{status}", statusText)
  } catch (err: any) {
    error.value = err.message || tt.value.updateApprovalFailed
  } finally {
    operatingId.value = null
  }
}

async function toggleActive(user: AccountUser) {
  error.value = ""
  successMsg.value = ""
  operatingId.value = user.id
  try {
    const nextActive = !user.is_active
    const updated = await patchAdminUser(user.id, { is_active: nextActive })
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx !== -1) users.value[idx] = updated
    const actionText = nextActive ? tt.value.actionEnabled : tt.value.actionDisabled
    successMsg.value = tt.value.userStatusUpdated.replace("{username}", user.username).replace("{action}", actionText)
  } catch (err: any) {
    error.value = err.message || tt.value.updateStatusFailed
  } finally {
    operatingId.value = null
  }
}

async function handleReset2fa(user: AccountUser) {
  if (!confirm(tt.value.confirmReset2faVue.replace("{username}", user.username))) {
    return
  }
  error.value = ""
  successMsg.value = ""
  operatingId.value = user.id
  try {
    await resetAdminUser2fa(user.id)
    successMsg.value = tt.value.reset2faSuccess.replace("{username}", user.username)
  } catch (err: any) {
    error.value = err.message || tt.value.reset2faFailed
  } finally {
    operatingId.value = null
  }
}

async function handleDeleteUser(user: AccountUser) {
  if (!confirm(tt.value.confirmDeleteUserVue.replace("{username}", user.username))) {
    return
  }
  error.value = ""
  successMsg.value = ""
  operatingId.value = user.id
  try {
    await deleteAdminUser(user.id)
    users.value = users.value.filter((u) => u.id !== user.id)
    successMsg.value = tt.value.deleteUserSuccess.replace("{username}", user.username)
  } catch (err: any) {
    error.value = err.message || tt.value.deleteUserFailed
  } finally {
    operatingId.value = null
  }
}

onMounted(() => {
  void loadUsers()
})
</script>
