<template>
  <header class="app-header">
    <div class="nav-container">
      <div class="brand-section">
        <router-link to="/" class="brand-link">
          <span style="font-size: 22px">🔐</span>
          <span>Account Kit</span>
        </router-link>
        <span v-if="!isInitialized" class="badge badge-yellow">未初始化</span>
        <span v-else class="badge badge-green">已连接</span>
      </div>

      <nav class="nav-links">
        <template v-if="!isInitialized">
          <router-link to="/setup" class="nav-item" active-class="active">初始化向导</router-link>
        </template>

        <template v-else>
          <template v-if="!isLoggedIn">
            <router-link to="/login" class="nav-item" active-class="active">登录</router-link>
            <router-link to="/register" class="nav-item" active-class="active">注册</router-link>
            <router-link to="/reset" class="nav-item" active-class="active">找回密码</router-link>
          </template>

          <template v-else>
            <router-link to="/account" class="nav-item" active-class="active">账号中心</router-link>
            <template v-if="currentUser?.is_admin">
              <router-link to="/admin" class="nav-item" :class="{ active: route.path === '/admin' }">
                用户管理
              </router-link>
              <router-link to="/admin/audit" class="nav-item" active-class="active">
                审计日志
              </router-link>
            </template>
          </template>

          <router-link to="/outbox" class="nav-item" active-class="active">站内信箱</router-link>
        </template>
      </nav>

      <div class="nav-actions">
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          title="打开右侧站内信箱抽屉"
          @click="toggleDrawer"
        >
          📬 验证码信箱
        </button>

        <template v-if="isLoggedIn">
          <span style="font-size: 13px; color: #4b5563; margin-left: 8px">
            <strong>{{ currentUser?.username || '用户' }}</strong>
            <span v-if="currentUser?.is_admin" class="badge badge-blue" style="margin-left: 4px">管理员</span>
          </span>
          <button type="button" class="btn btn-secondary btn-sm" style="margin-left: 6px" @click="handleLogout">
            退出
          </button>
        </template>
        <template v-else-if="isInitialized && route.path !== '/login'">
          <router-link to="/login" class="btn btn-outline btn-sm">登录</router-link>
        </template>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  setupStatus,
  currentUser,
  tokenStore,
  client,
  outboxDrawerOpen,
} from "../api"

const route = useRoute()
const router = useRouter()

const isInitialized = computed(() => !!setupStatus.value?.initialized)
const isLoggedIn = computed(() => !!tokenStore.getAccessToken())

function toggleDrawer() {
  outboxDrawerOpen.value = !outboxDrawerOpen.value
}

async function handleLogout() {
  const token = tokenStore.getAccessToken()
  const refreshToken = tokenStore.getRefreshToken()
  try {
    if (token) {
      await client.logout(token, { refreshToken: refreshToken || null })
    }
  } catch {
    // Ignore logout failure
  } finally {
    tokenStore.clear()
    currentUser.value = null
    router.push("/login")
  }
}
</script>
