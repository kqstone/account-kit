import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
import {
  fetchSetupStatus,
  setupStatus,
  tokenStore,
  refreshCurrentUser,
  currentUser,
} from "./api"
import { demoLocale, messages } from "./i18n"

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: () => {
      if (setupStatus.value && !setupStatus.value.initialized) {
        return "/setup"
      }
      return tokenStore.getAccessToken() ? "/account" : "/login"
    },
  },
  {
    path: "/setup",
    name: "Setup",
    component: () => import("./views/SetupView.vue"),
  },
  {
    path: "/login",
    name: "Login",
    component: () => import("./views/LoginView.vue"),
  },
  {
    path: "/register",
    name: "Register",
    component: () => import("./views/RegisterView.vue"),
  },
  {
    path: "/reset",
    name: "Reset",
    component: () => import("./views/ResetView.vue"),
  },
  {
    path: "/account",
    name: "Account",
    component: () => import("./views/AccountView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/admin",
    name: "AdminUsers",
    component: () => import("./views/AdminUsersView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/admin/audit",
    name: "AdminAudit",
    component: () => import("./views/AdminAuditView.vue"),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: "/outbox",
    name: "Outbox",
    component: () => import("./views/OutboxView.vue"),
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/",
  },
]

export const router = createRouter({
  history: createWebHistory("/"),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  try {
    if (!setupStatus.value) {
      await fetchSetupStatus()
    }
  } catch {
    // If fetching setup status fails, allow setup page
  }

  const isInitialized = !!setupStatus.value?.initialized

  // 1. If not initialized, force /setup
  if (!isInitialized) {
    if (to.path !== "/setup") {
      return next("/setup")
    }
    return next()
  }

  // 2. If initialized and user tries to access /setup, redirect to /login or /account
  if (to.path === "/setup") {
    return next(tokenStore.getAccessToken() ? "/account" : "/login")
  }

  // 3. Auth checks
  const token = tokenStore.getAccessToken()
  if (to.meta.requiresAuth) {
    if (!token) {
      return next({ path: "/login", query: { redirect: to.fullPath } })
    }
    if (to.meta.requiresAdmin) {
      if (!currentUser.value) {
        await refreshCurrentUser()
      }
      if (!currentUser.value?.is_admin) {
        alert(messages[demoLocale.value].requireAdminAlert)
        return next("/account")
      }
    }
  }

  next()
})
