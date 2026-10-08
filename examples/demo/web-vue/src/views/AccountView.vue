<template>
  <div class="page-container" style="max-width: 900px; margin: 0 auto">
    <!-- 用户信息头部卡片 -->
    <div class="card" style="display: flex; align-items: center; justify-content: space-between; gap: 20px; flex-wrap: wrap">
      <div style="display: flex; align-items: center; gap: 16px">
        <div style="width: 56px; height: 56px; border-radius: 50%; background: #e0e7ff; color: #4338ca; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 600">
          {{ (currentUser?.username || 'U')[0].toUpperCase() }}
        </div>
        <div>
          <div style="display: flex; align-items: center; gap: 8px">
            <h2 style="font-size: 20px; font-weight: 700; color: #111827">
              {{ currentUser?.username }}
            </h2>
            <TierBadge
              v-if="currentUser?.tier_name"
              :name="currentUser.tier_name"
              :color="currentUser.tier_badge_color || '#8c8c8c'"
            />
            <span v-if="currentUser?.is_admin" class="badge badge-blue">管理员</span>
            <span v-if="currentUser?.approval_status === 'approved'" class="badge badge-green">已通过审批</span>
            <span v-else-if="currentUser?.approval_status === 'pending'" class="badge badge-yellow">审批中</span>
          </div>
          <div style="font-size: 14px; color: var(--color-text-secondary); margin-top: 4px">
            <span>邮箱: {{ currentUser?.email }}</span>
            <span style="margin: 0 8px">·</span>
            <span>角色: {{ currentUser?.role || '默认' }}</span>
          </div>
        </div>
      </div>

      <div style="display: flex; align-items: center; gap: 10px">
        <LogoutButton
          :client="client"
          :token="token"
          :refresh-token="refreshToken"
          
          @done="handleLogoutDone"
        />
        <LogoutButton
          :client="client"
          :token="token"
          :refresh-token="refreshToken"
          :all-devices="true"
          
          @done="handleLogoutDone"
        >
          全部设备登出
        </LogoutButton>
      </div>
    </div>

    <!-- 导航标签 -->
    <div class="tabs">
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === 'profile' }"
        @click="currentTab = 'profile'"
      >
        个人资料与密码
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === 'email' }"
        @click="currentTab = 'email'"
      >
        修改邮箱
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === '2fa' }"
        @click="currentTab = '2fa'"
      >
        两步验证 (2FA)
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === 'danger' }"
        @click="currentTab = 'danger'"
      >
        危险操作
      </button>
    </div>

    <!-- 1. 资料与密码 -->
    <div v-show="currentTab === 'profile'" class="card">
      <h3 class="card-title">基本资料与修改密码</h3>
      <p class="card-subtitle">
        更新姓名、性别、机构及登录密码。修改密码可按需校验邮箱验证码。
      </p>

      <div class="outbox-hint-banner" style="margin-bottom: 20px">
        <span>📬 若修改密码需要验证码，请在站内信箱查看</span>
        <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
          查看信箱
        </button>
      </div>

      <ProfileFields
        v-if="currentUser"
        :client="client"
        :token="token"
        :user="currentUser"
        
        password-email-code="auto"
        @saved="handleProfileSaved"
        @password-changed="handlePasswordChanged"
      />
    </div>

    <!-- 2. 修改邮箱 -->
    <div v-show="currentTab === 'email'" class="card">
      <h3 class="card-title">修改绑定邮箱</h3>
      <p class="card-subtitle">
        系统将发送 6 位验证码到新邮箱以确认所有权。当前 demo 运行在 console 邮件模式下，可直接在站内信箱查看验证码。
      </p>

      <div class="outbox-hint-banner" style="margin-bottom: 20px">
        <span>📬 发送改邮验证码后，请在站内信箱复制</span>
        <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
          查看信箱
        </button>
      </div>

      <ChangeEmailForm
        v-if="currentUser"
        :client="client"
        :token="token"
        :user="currentUser"
        :require-password="true"
        
        @changed="handleEmailChanged"
      />
    </div>

    <!-- 3. 两步验证 (2FA) -->
    <div v-show="currentTab === '2fa'" class="card">
      <h3 class="card-title">两步验证设置 (2FA)</h3>
      <p class="card-subtitle">
        使用 TOTP 身份验证器（如 Google Authenticator）为您的账号增加安全保护。
      </p>

      <div class="outbox-hint-banner" style="margin-bottom: 20px">
        <span>📬 若选择邮箱验证码关闭或重置 2FA，可在信箱获取验证码</span>
        <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
          查看信箱
        </button>
      </div>

      <TwoFactorSettings
        v-if="currentUser"
        :client="client"
        :token="token"
        :username="currentUser.username"
        
        @updated="handleTwoFactorUpdated"
      />
    </div>

    <!-- 4. 危险操作 (注销账号) -->
    <div v-show="currentTab === 'danger'" class="card">
      <h3 class="card-title" style="color: var(--color-danger)">注销账号</h3>
      <p class="card-subtitle">
        注销账号为不可逆操作。注销后所有个人数据将被清除。
      </p>

      <div v-if="currentUser?.is_admin" class="alert alert-warning">
        当前账号具有管理员权限。出于安全保护，系统禁止管理员自助注销账号（如需注销，请由其他管理员操作）。
      </div>

      <template v-else>
        <div class="outbox-hint-banner" style="margin-bottom: 20px">
          <span>📬 若开启了 2FA 且选择邮箱验证码注销，请在信箱获取验证码</span>
          <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
            查看信箱
          </button>
        </div>

        <DeleteAccountForm
          :client="client"
          :token="token"
          :two-factor-enabled="tfStatus?.enabled || false"
          :email-code-available="tfStatus?.email_available || false"
          
          @deleted="handleAccountDeleted"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { useRouter } from "vue-router"
import {
  ProfileFields,
  ChangeEmailForm,
  TwoFactorSettings,
  LogoutButton,
  DeleteAccountForm,
  TierBadge,
  type TwoFactorStatus,
  type ProfileUpdateResult,
  type AccountUser,
} from "@kqstone/account-ui-vue"
import {
  client,
  tokenStore,
  currentUser,
  refreshCurrentUser,
  outboxDrawerOpen,
} from "../api"

const router = useRouter()
const currentTab = ref<"profile" | "email" | "2fa" | "danger">("profile")
const tfStatus = ref<TwoFactorStatus | null>(null)

const token = computed(() => tokenStore.getAccessToken() || "")
const refreshToken = computed(() => tokenStore.getRefreshToken() || "")

function openDrawer() {
  outboxDrawerOpen.value = true
}

async function loadTwoFactorStatus() {
  if (!token.value) return
  try {
    tfStatus.value = await client.twoFactorStatus(token.value)
  } catch {
    // Ignore error
  }
}

function handleProfileSaved(result?: ProfileUpdateResult) {
  if (result?.user) {
    currentUser.value = result.user
  } else {
    void refreshCurrentUser()
  }
}

function handlePasswordChanged() {
  void refreshCurrentUser()
}

function handleEmailChanged(updatedUser: AccountUser) {
  currentUser.value = updatedUser
}

function handleTwoFactorUpdated(status: TwoFactorStatus) {
  tfStatus.value = status
}

function handleLogoutDone() {
  tokenStore.clear()
  currentUser.value = null
  router.push("/login")
}

function handleAccountDeleted() {
  tokenStore.clear()
  currentUser.value = null
  alert("您的账号已成功注销")
  router.push("/login")
}

onMounted(async () => {
  await refreshCurrentUser()
  await loadTwoFactorStatus()
})
</script>
