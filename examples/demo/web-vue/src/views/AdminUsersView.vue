<template>
  <div class="page-container">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px">
        <div>
          <h1 class="card-title" style="margin-bottom: 4px">用户管理</h1>
          <p class="card-subtitle" style="margin-bottom: 0">
            查看并管理系统用户列表，处理新注册审批、启停账号以及重置 2FA。管理员由初始化写入，不能通过接口改 is_admin。
          </p>
        </div>
        <div style="display: flex; gap: 10px">
          <router-link to="/admin/audit" class="btn btn-secondary">
            📋 查看审计日志
          </router-link>
          <button type="button" class="btn btn-secondary" :disabled="loading" @click="loadUsers">
            {{ loading ? '加载中…' : '🔄 刷新用户列表' }}
          </button>
        </div>
      </div>

      <div v-if="error" class="alert alert-error">
        {{ error }}
      </div>

      <div v-if="successMsg" class="alert alert-success">
        {{ successMsg }}
      </div>

      <!-- 搜索与筛选 -->
      <div style="display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap">
        <input
          v-model="searchTerm"
          type="text"
          placeholder="搜索用户名或邮箱…"
          class="form-input"
          style="max-width: 260px"
        />
        <select v-model="statusFilter" class="form-select" style="max-width: 180px">
          <option value="">全部审批状态</option>
          <option value="pending">待审批 (pending)</option>
          <option value="approved">已批准 (approved)</option>
          <option value="rejected">已拒绝 (rejected)</option>
        </select>
      </div>

      <!-- 用户表格 -->
      <div class="table-container">
        <table class="table">
          <thead>
            <tr>
              <th>用户名 / 姓名</th>
              <th>邮箱</th>
              <th>角色</th>
              <th>等级</th>
              <th>审批状态</th>
              <th>账号状态</th>
              <th>管理员</th>
              <th style="text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && users.length === 0">
              <td colspan="8" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                正在加载用户数据…
              </td>
            </tr>
            <tr v-else-if="filteredUsers.length === 0">
              <td colspan="8" style="text-align: center; padding: 30px; color: var(--color-text-muted)">
                未找到匹配的用户记录
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
                  {{ user.tier_name || user.tier || '免费版' }}
                </span>
              </td>
              <td>
                <span v-if="user.approval_status === 'approved'" class="badge badge-green">已通过</span>
                <span v-else-if="user.approval_status === 'pending'" class="badge badge-yellow">待审批</span>
                <span v-else class="badge badge-red">已拒绝</span>
              </td>
              <td>
                <span v-if="user.is_active" class="badge badge-green">正常</span>
                <span v-else class="badge badge-red">已停用</span>
              </td>
              <td>
                <span v-if="user.is_admin" class="badge badge-blue">管理员</span>
                <span v-else style="color: var(--color-text-muted); font-size: 13px">否</span>
              </td>
              <td style="text-align: right">
                <div style="display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap">
                  <!-- 审批操作 -->
                  <template v-if="!user.is_admin && user.approval_status === 'pending'">
                    <button
                      type="button"
                      class="btn btn-sm"
                      style="background-color: #52c41a"
                      :disabled="operatingId === user.id"
                      @click="updateApproval(user, 'approved')"
                    >
                      通过
                    </button>
                    <button
                      type="button"
                      class="btn btn-secondary btn-sm"
                      :disabled="operatingId === user.id"
                      @click="updateApproval(user, 'rejected')"
                    >
                      拒绝
                    </button>
                  </template>
                  <template v-else-if="!user.is_admin && user.approval_status === 'rejected'">
                    <button
                      type="button"
                      class="btn btn-sm"
                      :disabled="operatingId === user.id"
                      @click="updateApproval(user, 'approved')"
                    >
                      重新通过
                    </button>
                  </template>

                  <!-- 启停状态 -->
                  <button
                    v-if="!user.is_admin"
                    type="button"
                    class="btn btn-secondary btn-sm"
                    :disabled="operatingId === user.id"
                    @click="toggleActive(user)"
                  >
                    {{ user.is_active ? '停用' : '启用' }}
                  </button>

                  <!-- 重置 2FA -->
                  <button
                    type="button"
                    class="btn btn-secondary btn-sm"
                    title="重置该用户的两步验证并注销其刷新令牌"
                    :disabled="operatingId === user.id"
                    @click="handleReset2fa(user)"
                  >
                    重置2FA
                  </button>

                  <!-- 删除 -->
                  <button
                    v-if="!user.is_admin"
                    type="button"
                    class="btn btn-danger-outline btn-sm"
                    :disabled="operatingId === user.id"
                    @click="handleDeleteUser(user)"
                  >
                    删除
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
    error.value = err.message || "加载用户列表失败"
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
    successMsg.value = `用户 ${user.username} 的审批状态已更新为「${status === 'approved' ? '已通过' : '已拒绝'}」`
  } catch (err: any) {
    error.value = err.message || "更新审批状态失败"
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
    successMsg.value = `用户 ${user.username} 已${nextActive ? '启用' : '停用'}`
  } catch (err: any) {
    error.value = err.message || "更新用户状态失败"
  } finally {
    operatingId.value = null
  }
}

async function handleReset2fa(user: AccountUser) {
  if (!confirm(`确定重置用户 ${user.username} 的两步验证 (2FA) 吗？该用户的所有两步验证密钥将失效并需重新配置。`)) {
    return
  }
  error.value = ""
  successMsg.value = ""
  operatingId.value = user.id
  try {
    await resetAdminUser2fa(user.id)
    successMsg.value = `已成功重置用户 ${user.username} 的两步验证`
  } catch (err: any) {
    error.value = err.message || "重置 2FA 失败"
  } finally {
    operatingId.value = null
  }
}

async function handleDeleteUser(user: AccountUser) {
  if (!confirm(`确定删除用户 ${user.username} 吗？此操作不可撤销！`)) {
    return
  }
  error.value = ""
  successMsg.value = ""
  operatingId.value = user.id
  try {
    await deleteAdminUser(user.id)
    users.value = users.value.filter((u) => u.id !== user.id)
    successMsg.value = `用户 ${user.username} 已被删除`
  } catch (err: any) {
    error.value = err.message || "删除用户失败"
  } finally {
    operatingId.value = null
  }
}

onMounted(() => {
  void loadUsers()
})
</script>
