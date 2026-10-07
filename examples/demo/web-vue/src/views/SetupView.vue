<template>
  <div class="page-container" style="max-width: 720px; margin: 0 auto">
    <div class="card">
      <h1 class="card-title" style="font-size: 24px; display: flex; align-items: center; gap: 8px">
        <span>🚀</span>
        <span>Account Kit 初始化向导</span>
      </h1>
      <p class="card-subtitle">
        欢迎使用 account-kit 单页演示前端。首次运行请配置 PostgreSQL 数据库连接、初始管理员账号以及各项安全特性开关。
      </p>

      <div v-if="setupStatus?.initialized" class="alert alert-info">
        <div>
          <strong>系统已完成初始化！</strong>
          <p style="margin-top: 4px; font-size: 13px">
            数据库与功能开关已就绪。如需使用，请直接登录。
          </p>
          <div style="margin-top: 10px">
            <router-link to="/login" class="btn btn-sm">前往登录</router-link>
          </div>
        </div>
      </div>

      <div v-if="globalError" class="alert alert-error">
        {{ globalError }}
      </div>

      <div v-if="testDbSuccess" class="alert alert-success">
        ✓ 数据库连接测试成功，服务可正常访问！
      </div>

      <form v-if="!setupStatus?.initialized" @submit.prevent="handleInit">
        <!-- 1. 数据库配置 -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 20px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            1. PostgreSQL 数据库
          </legend>

          <div class="form-row">
            <div class="form-group" style="flex: 2">
              <label class="form-label">主机 (Host)</label>
              <input v-model="form.db.host" type="text" required class="form-input" />
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">端口 (Port)</label>
              <input v-model.number="form.db.port" type="number" required class="form-input" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group" style="flex: 1">
              <label class="form-label">用户名 (User)</label>
              <input v-model="form.db.user" type="text" required class="form-input" />
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">密码 (Password)</label>
              <input v-model="form.db.password" type="password" class="form-input" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">数据库名 (Database)</label>
            <input v-model="form.db.database" type="text" required class="form-input" />
          </div>

          <div style="display: flex; justify-content: flex-end">
            <button
              type="button"
              class="btn btn-secondary btn-sm"
              :disabled="testingDb"
              @click="handleTestDb"
            >
              {{ testingDb ? '正在测试连接…' : '🔌 测试数据库连接' }}
            </button>
          </div>
        </fieldset>

        <!-- 2. 管理员配置 -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 20px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            2. 初始管理员账号
          </legend>

          <div class="form-row">
            <div class="form-group" style="flex: 1">
              <label class="form-label">管理员用户名</label>
              <input v-model="form.admin.username" type="text" required minlength="1" class="form-input" />
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">管理员邮箱</label>
              <input v-model="form.admin.email" type="email" required class="form-input" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">管理员密码 (至少 6 位)</label>
            <input v-model="form.admin.password" type="password" required minlength="6" class="form-input" />
          </div>
        </fieldset>

        <!-- 3. 功能开关 -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 20px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            3. 安全与特性开关
          </legend>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">刷新令牌 (refresh)</div>
              <div class="form-switch-desc">启用 access/refresh 令牌双轨轮换机制</div>
            </div>
            <input v-model="form.features.refresh" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">图形验证码 (captcha)</div>
              <div class="form-switch-desc">多次登录失败后强制输入图片验证码</div>
            </div>
            <input v-model="form.features.captcha" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">允许自助注销账号 (self_delete)</div>
              <div class="form-switch-desc">普通用户可在账号页自主申请删除账号</div>
            </div>
            <input v-model="form.features.self_delete" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">邮箱两步验证码 (two_factor_email)</div>
              <div class="form-switch-desc">允许使用邮箱验证码作为 2FA 第二因素</div>
            </div>
            <input v-model="form.features.two_factor_email" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">新注册需审批 (require_approval)</div>
              <div class="form-switch-desc">开启后用户注册为 pending 状态，需管理员后台批准后方可登录</div>
            </div>
            <input v-model="form.features.require_approval" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">两步验证 (two_factor)</div>
              <div class="form-switch-desc">启用 TOTP / 恢复码双因素认证模块</div>
            </div>
            <input v-model="form.features.two_factor" type="checkbox" />
          </div>

          <div class="form-switch">
            <div>
              <div style="font-size: 14px; font-weight: 500">审计日志 (audit_log)</div>
              <div class="form-switch-desc">记录用户登录、修改密码、2FA 变更等安全审计</div>
            </div>
            <input v-model="form.features.audit_log" type="checkbox" />
          </div>

          <div class="form-row" style="margin-top: 12px">
            <div class="form-group" style="flex: 1">
              <label class="form-label">会话模式 (Session Mode)</label>
              <select v-model="form.features.session_mode" class="form-select">
                <option value="stateless">stateless (多设备无状态)</option>
                <option value="single_device">single_device (单设备互顶)</option>
              </select>
            </div>
            <div class="form-group" style="flex: 1">
              <label class="form-label">验证码触发失败阈值</label>
              <input v-model.number="form.features.captcha_fail_threshold" type="number" min="1" class="form-input" />
            </div>
          </div>
        </fieldset>

        <!-- 4. 邮件模式 -->
        <fieldset style="border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; margin-bottom: 24px">
          <legend style="font-weight: 600; font-size: 15px; padding: 0 8px; color: #111827">
            4. 邮件发送模式
          </legend>

          <div class="form-group">
            <div style="display: flex; gap: 20px; margin-top: 4px">
              <label style="display: flex; align-items: center; gap: 6px; cursor: pointer">
                <input v-model="form.mail_mode" type="radio" value="console" />
                <span><strong>console</strong>（推荐：打印并在站内信箱查看）</span>
              </label>
              <label style="display: flex; align-items: center; gap: 6px; cursor: pointer">
                <input v-model="form.mail_mode" type="radio" value="smtp" />
                <span><strong>smtp</strong>（通过真实 SMTP 服务器发信）</span>
              </label>
            </div>
          </div>

          <div v-if="form.mail_mode === 'smtp'" style="margin-top: 16px; border-top: 1px dashed var(--color-border); padding-top: 12px">
            <div class="form-row">
              <div class="form-group" style="flex: 2">
                <label class="form-label">SMTP 主机</label>
                <input v-model="form.smtp.host" type="text" placeholder="127.0.0.1" class="form-input" />
              </div>
              <div class="form-group" style="flex: 1">
                <label class="form-label">端口</label>
                <input v-model.number="form.smtp.port" type="number" placeholder="1025" class="form-input" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group" style="flex: 1">
                <label class="form-label">发件人地址</label>
                <input v-model="form.smtp.from_email" type="email" placeholder="demo@example.com" class="form-input" />
              </div>
              <div class="form-group" style="flex: 1">
                <label class="form-label">TLS 加密</label>
                <select v-model="form.smtp.tls" class="form-select">
                  <option :value="false">关 (明文/STARTTLS)</option>
                  <option :value="true">开 (SSL/TLS)</option>
                </select>
              </div>
            </div>
          </div>
        </fieldset>

        <div style="display: flex; justify-content: flex-end; gap: 12px">
          <button type="submit" class="btn" :disabled="submitting" style="padding: 10px 24px; font-size: 15px">
            {{ submitting ? '正在初始化系统…' : '✓ 提交并初始化' }}
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
    globalError.value = err.message || "数据库连接测试失败"
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
    globalError.value = err.message || "初始化失败"
  } finally {
    submitting.value = false
  }
}
</script>
