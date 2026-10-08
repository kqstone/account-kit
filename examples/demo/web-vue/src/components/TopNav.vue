<template>
  <header class="app-header">
    <div class="nav-container">
      <div class="brand-section">
        <router-link to="/" class="brand-link">
          <span style="font-size: 22px">🔐</span>
          <span>Account Kit</span>
        </router-link>
        <span v-if="!isInitialized" class="badge badge-yellow">{{ tt.notInit }}</span>
        <span v-else class="badge badge-green">{{ tt.connected }}</span>
      </div>

      <nav class="nav-links">
        <template v-if="!isInitialized">
          <router-link to="/setup" class="nav-item" active-class="active">{{ tt.setup }}</router-link>
        </template>

        <template v-else>
          <template v-if="!isLoggedIn">
            <router-link to="/login" class="nav-item" active-class="active">{{ tt.login }}</router-link>
            <router-link to="/register" class="nav-item" active-class="active">{{ tt.register }}</router-link>
            <router-link to="/reset" class="nav-item" active-class="active">{{ tt.reset }}</router-link>
          </template>

          <template v-else>
            <router-link to="/account" class="nav-item" active-class="active">{{ tt.account }}</router-link>
            <template v-if="currentUser?.is_admin">
              <router-link to="/admin" class="nav-item" :class="{ active: route.path === '/admin' }">
                {{ tt.adminUsers }}
              </router-link>
              <router-link to="/admin/audit" class="nav-item" active-class="active">
                {{ tt.adminAudit }}
              </router-link>
            </template>
          </template>

          <router-link to="/outbox" class="nav-item" active-class="active">{{ tt.outbox }}</router-link>
        </template>
      </nav>

      <div class="nav-actions">
        <div class="lang-switch" role="group" :aria-label="tt.langZh + ' / ' + tt.langEn">
          <button type="button" :class="{ active: demoLocale === 'zh-CN' }" @click="setDemoLocale('zh-CN')">
            {{ tt.langZh }}
          </button>
          <button type="button" :class="{ active: demoLocale === 'en' }" @click="setDemoLocale('en')">
            {{ tt.langEn }}
          </button>
        </div>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          :title="tt.drawerTitle"
          @click="toggleDrawer"
        >
          📬 {{ tt.drawerMailbox }}
        </button>

        <template v-if="isLoggedIn">
          <span style="font-size: 13px; color: #4b5563; margin-left: 8px">
            <strong>{{ currentUser?.username || '用户' }}</strong>
            <span v-if="currentUser?.is_admin" class="badge badge-blue" style="margin-left: 4px">{{ tt.admin }}</span>
          </span>
          <button type="button" class="btn btn-secondary btn-sm" style="margin-left: 6px" @click="handleLogout">
            {{ tt.logout }}
          </button>
        </template>
        <template v-else-if="isInitialized && route.path !== '/login'">
          <router-link to="/login" class="btn btn-outline btn-sm">{{ tt.login }}</router-link>
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
import { demoLocale, setDemoLocale, tt } from "../i18n"

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
