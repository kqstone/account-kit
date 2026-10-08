<template>
  <div class="page-container" style="max-width: 900px; margin: 0 auto">
    <!-- User header card -->
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
            <span v-if="currentUser?.is_admin" class="badge badge-blue">{{ tt.admin }}</span>
            <span v-if="currentUser?.approval_status === 'approved'" class="badge badge-green">{{ tt.approved }}</span>
            <span v-else-if="currentUser?.approval_status === 'pending'" class="badge badge-yellow">{{ tt.pending }}</span>
          </div>
          <div style="font-size: 14px; color: var(--color-text-secondary); margin-top: 4px">
            <span>{{ tt.emailLabel }}: {{ currentUser?.email }}</span>
            <span style="margin: 0 8px">·</span>
            <span>{{ tt.roleLabel }}: {{ currentUser?.role || tt.roleDefault }}</span>
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
          {{ tt.logoutAll }}
        </LogoutButton>
      </div>
    </div>

    <!-- Navigation tabs -->
    <div class="tabs">
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === 'profile' }"
        @click="currentTab = 'profile'"
      >
        {{ tt.tabProfilePassword }}
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === 'email' }"
        @click="currentTab = 'email'"
      >
        {{ tt.tabEmail }}
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === '2fa' }"
        @click="currentTab = '2fa'"
      >
        {{ tt.tab2fa }}
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: currentTab === 'danger' }"
        @click="currentTab = 'danger'"
      >
        {{ tt.tabDanger }}
      </button>
    </div>

    <!-- 1. Profile & Password -->
    <div v-show="currentTab === 'profile'" class="card">
      <h3 class="card-title">{{ tt.accountProfileHeading }}</h3>
      <p class="card-subtitle">
        {{ tt.accountProfileDesc }}
      </p>

      <div class="outbox-hint-banner" style="margin-bottom: 20px">
        <span>{{ tt.accountMailboxPasswordTip }}</span>
        <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
          {{ tt.viewMailbox }}
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

    <!-- 2. Change Email -->
    <div v-show="currentTab === 'email'" class="card">
      <h3 class="card-title">{{ tt.accountEmailHeading }}</h3>
      <p class="card-subtitle">
        {{ tt.accountEmailDesc }}
      </p>

      <div class="outbox-hint-banner" style="margin-bottom: 20px">
        <span>{{ tt.accountMailboxEmailTip }}</span>
        <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
          {{ tt.viewMailbox }}
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

    <!-- 3. Two-Factor (2FA) -->
    <div v-show="currentTab === '2fa'" class="card">
      <h3 class="card-title">{{ tt.account2faHeading }}</h3>
      <p class="card-subtitle">
        {{ tt.account2faDesc }}
      </p>

      <div class="outbox-hint-banner" style="margin-bottom: 20px">
        <span>{{ tt.accountMailbox2faTip }}</span>
        <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
          {{ tt.viewMailbox }}
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

    <!-- 4. Danger Zone (Delete Account) -->
    <div v-show="currentTab === 'danger'" class="card">
      <h3 class="card-title" style="color: var(--color-danger)">{{ tt.deleteAccountTitle }}</h3>
      <p class="card-subtitle">
        {{ tt.deleteAccountDesc }}
      </p>

      <div v-if="currentUser?.is_admin" class="alert alert-warning">
        {{ tt.deleteAccountAdminBlocked }}
      </div>

      <template v-else>
        <div class="outbox-hint-banner" style="margin-bottom: 20px">
          <span>{{ tt.accountMailboxDeleteTip }}</span>
          <button type="button" class="btn btn-secondary btn-sm" @click="openDrawer">
            {{ tt.viewMailbox }}
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
import { tt } from "../i18n"

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
  alert(tt.value.accountDeletedAlert)
  router.push("/login")
}

onMounted(async () => {
  await refreshCurrentUser()
  await loadTwoFactorStatus()
})
</script>
