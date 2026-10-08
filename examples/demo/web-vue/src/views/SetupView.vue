<template>
  <div class="page-container" style="max-width: 720px; margin: 0 auto">
    <div class="card">
      <h1 class="card-title" style="font-size: 24px; display: flex; align-items: center; gap: 8px">
        <span>🚀</span>
        <span>{{ tt.setupHeading }}</span>
      </h1>
      <p class="card-subtitle">
        {{ tt.setupDesc }}
      </p>

      <div v-if="setupStatus?.initialized" class="alert alert-info">
        <div>
          <strong>{{ tt.setupAlreadyInitTitle }}</strong>
          <p style="margin-top: 4px; font-size: 13px">
            {{ tt.setupAlreadyInitDesc }}
          </p>
          <div style="margin-top: 10px">
            <router-link to="/login" class="btn btn-sm">{{ tt.goLoginBtn }}</router-link>
          </div>
        </div>
      </div>

      <div v-if="globalError" class="alert alert-error">
        {{ globalError }}
      </div>

      <div v-if="testDbSuccess" class="alert alert-success">
        {{ tt.dbTestSuccessVue }}
      </div>

      <form v-if="!setupStatus?.initialized" @submit.prevent="handleInit">
        <!-- 1. Database config -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 20px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            {{ tt.sec1DbVue }}
          </legend>

          <div class="form-row">
            <div class="form-group" style="flex: 2">
              <label class="form-label">{{ tt.dbHost }}</label>
              <input v-model="form.db.host" type="text" required class="form-input" />
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">{{ tt.dbPort }}</label>
              <input v-model.number="form.db.port" type="number" required class="form-input" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group" style="flex: 1">
              <label class="form-label">{{ tt.dbUser }}</label>
              <input v-model="form.db.user" type="text" required class="form-input" />
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">{{ tt.dbPassword }}</label>
              <input v-model="form.db.password" type="password" class="form-input" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">{{ tt.dbName }}</label>
            <input v-model="form.db.database" type="text" required class="form-input" />
          </div>

          <div style="display: flex; justify-content: flex-end">
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              :disabled="testingDb"
              @click="handleTestDb"
            >
              {{ testingDb ? tt.testingDbVue : tt.btnTestDbVue }}
            </button>
          </div>
        </fieldset>

        <!-- 2. Admin config -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 20px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            {{ tt.sec2AdminVue }}
          </legend>

          <div class="form-row">
            <div class="form-group" style="flex: 1">
              <label class="form-label">{{ tt.adminUsername }}</label>
              <input v-model="form.admin.username" type="text" required minlength="1" class="form-input" />
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">{{ tt.adminEmail }}</label>
              <input v-model="form.admin.email" type="email" required class="form-input" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">{{ tt.adminPassword }}</label>
            <input v-model="form.admin.password" type="password" required minlength="6" class="form-input" />
          </div>
        </fieldset>

        <!-- 3. Features -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 20px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            {{ tt.sec3FeaturesVue }}
          </legend>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">{{ tt.featRefreshVue }}</div>
              <div class="form-switch-desc">{{ tt.featRefreshDescVue }}</div>
            </div>
            <input v-model="form.features.refresh" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">{{ tt.featCaptchaVue }}</div>
              <div class="form-switch-desc">{{ tt.featCaptchaDescVue }}</div>
            </div>
            <input v-model="form.features.captcha" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">{{ tt.featSelfDeleteVue }}</div>
              <div class="form-switch-desc">{{ tt.featSelfDeleteDescVue }}</div>
            </div>
            <input v-model="form.features.self_delete" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">{{ tt.featTwoFactorEmailVue }}</div>
              <div class="form-switch-desc">{{ tt.featTwoFactorEmailDescVue }}</div>
            </div>
            <input v-model="form.features.two_factor_email" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">{{ tt.featRequireApprovalVue }}</div>
              <div class="form-switch-desc">{{ tt.featRequireApprovalDesc }}</div>
            </div>
            <input v-model="form.features.require_approval" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">{{ tt.featTwoFactorVue }}</div>
              <div class="form-switch-desc">{{ tt.featTwoFactorDescVue }}</div>
            </div>
            <input v-model="form.features.two_factor" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">{{ tt.featAuditLogVue }}</div>
              <div class="form-switch-desc">{{ tt.featAuditLogDescVue }}</div>
            </div>
            <input v-model="form.features.audit_log" type="checkbox" />
          </div>

          <div class="form-row" style="margin-top: 12px">
            <div class="form-group" style="flex: 1">
              <label class="form-label">{{ tt.sessionModeLabel }}</label>
              <select v-model="form.features.session_mode" class="form-select">
                <option value="stateless">{{ tt.sessionModeStateless }}</option>
                <option value="single_device">{{ tt.sessionModeSingle }}</option>
              </select>
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">{{ tt.captchaThresholdLabel }}</label>
              <input v-model.number="form.features.captcha_fail_threshold" type="number" min="1" class="form-input" />
            </div>
          </div>
        </fieldset>

        <!-- 4. Mail mode -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 24px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            {{ tt.sec4MailVue }}
          </legend>

          <div class="form-group">
            <div style="display: flex; gap: 20px; margin-top: 4px">
              <label style="display: flex; align-items: center; gap: 6px; cursor: pointer">
                <input v-model="form.mail_mode" type="radio" value="console" />
                <span>{{ tt.mailConsoleVue }}</span>
              </label>
              <label style="display: flex; align-items: center; gap: 6px; cursor: pointer">
                <input v-model="form.mail_mode" type="radio" value="smtp" />
                <span>{{ tt.mailSmtpVue }}</span>
              </label>
            </div>
          </div>

          <div v-if="form.mail_mode === 'smtp'" style="margin-top: 16px; border-top: 1px dashed var(--color-border); padding-top: 12px">
            <div class="form-row">
              <div class="form-group" style="flex: 2">
                <label class="form-label">{{ tt.smtpHost }}</label>
                <input v-model="form.smtp.host" type="text" placeholder="127.0.0.1" class="form-input" />
              </div>
              <div class="form-group" style="flex: 1">
                <label class="form-label">{{ tt.smtpPort }}</label>
                <input v-model.number="form.smtp.port" type="number" placeholder="1025" class="form-input" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group" style="flex: 1">
                <label class="form-label">{{ tt.smtpSender }}</label>
                <input v-model="form.smtp.from_email" type="email" placeholder="demo@example.com" class="form-input" />
              </div>
              <div class="form-group" style="flex: 1">
                <label class="form-label">{{ tt.smtpTls }}</label>
                <select v-model="form.smtp.tls" class="form-select">
                  <option :value="false">{{ tt.tlsOff }}</option>
                  <option :value="true">{{ tt.tlsOn }}</option>
                </select>
              </div>
            </div>
          </div>
        </fieldset>

        <div style="display: flex; justify-content: flex-end; gap: 12px">
          <button type="submit" class="btn" :disabled="submitting" style="padding: 10px 24px; font-size: 15px">
            {{ submitting ? tt.submittingSetup : tt.submitAndInitBtnVue }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { setupStatus, testDb, initSystem } from "../api"
import { tt } from "../i18n"

const router = useRouter()

const testingDb = ref(false)
const testDbSuccess = ref(false)
const submitting = ref(false)
const globalError = ref("")

const form = reactive({
  db: {
    host: "127.0.0.1",
    port: 5432,
    user: "postgres",
    password: "postgres",
    database: "akdemo",
  },
  admin: {
    username: "demo-admin",
    email: "admin@example.com",
    password: "secret1a",
  },
  features: {
    refresh: true,
    captcha: true,
    self_delete: true,
    two_factor_email: true,
    require_approval: false,
    two_factor: true,
    logout: true,
    audit_log: true,
    role_change: true,
    session_mode: "stateless",
    captcha_fail_threshold: 3,
  },
  mail_mode: "console",
  smtp: {
    host: "127.0.0.1",
    port: 1025,
    user: "",
    password: "",
    from_email: "demo@example.com",
    tls: false,
  },
})

async function handleTestDb() {
  globalError.value = ""
  testDbSuccess.value = false
  testingDb.value = true
  try {
    await testDb(form.db)
    testDbSuccess.value = true
  } catch (err: any) {
    globalError.value = err.message || tt.value.dbTestFailed
  } finally {
    testingDb.value = false
  }
}

async function handleInit() {
  globalError.value = ""
  submitting.value = true
  try {
    const payload: Record<string, any> = {
      db: form.db,
      admin: form.admin,
      features: form.features,
      mail_mode: form.mail_mode,
    }
    if (form.mail_mode === "smtp") {
      payload.smtp = form.smtp
    }
    await initSystem(payload)
    router.push("/login")
  } catch (err: any) {
    globalError.value = err.message || tt.value.setupInitFailed
  } finally {
    submitting.value = false
  }
}
</script>
