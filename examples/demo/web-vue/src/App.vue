<template>
  <div class="app-layout">
    <TopNav />
    <main class="app-main">
      <router-view />
    </main>
    <OutboxDrawer />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue"
import TopNav from "./components/TopNav.vue"
import OutboxDrawer from "./components/OutboxDrawer.vue"
import { fetchSetupStatus, refreshCurrentUser, tokenStore } from "./api"

onMounted(async () => {
  try {
    await fetchSetupStatus()
  } catch {
    // Ignore error
  }
  if (tokenStore.getAccessToken()) {
    try {
      await refreshCurrentUser()
    } catch {
      // Ignore error
    }
  }
})
</script>
