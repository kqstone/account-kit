import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { initSetup, testDatabase } from '../lib/api'
import { useDemoI18n } from '../lib/i18n'

export const SetupPage: React.FC = () => {
  const { setInitialized } = useAuth()
  const { t } = useDemoI18n()
  const navigate = useNavigate()

  // Postgres DB State
  const [dbHost, setDbHost] = useState('127.0.0.1')
  const [dbPort, setDbPort] = useState('5432')
  const [dbUser, setDbUser] = useState('postgres')
  const [dbPassword, setDbPassword] = useState('postgres')
  const [dbName, setDbName] = useState('akdemo')

  // DB test status
  const [testingDb, setTestingDb] = useState(false)
  const [dbTestMessage, setDbTestMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  // Admin Account State
  const [adminUsername, setAdminUsername] = useState('demo-admin')
  const [adminEmail, setAdminEmail] = useState('admin@example.com')
  const [adminPassword, setAdminPassword] = useState('secret1a')

  // Features Switches State
  const [featureRefresh, setFeatureRefresh] = useState(true)
  const [featureCaptcha, setFeatureCaptcha] = useState(true)
  const [featureSelfDelete, setFeatureSelfDelete] = useState(true)
  const [featureTwoFactorEmail, setFeatureTwoFactorEmail] = useState(true)
  const [featureRequireApproval, setFeatureRequireApproval] = useState(false)

  // Mail Mode State
  const [mailMode] = useState('console')

  // Submission State
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const handleTestDb = async () => {
    setTestingDb(true)
    setDbTestMessage(null)
    try {
      await testDatabase({
        host: dbHost.trim(),
        port: parseInt(dbPort.trim(), 10) || 5432,
        user: dbUser.trim(),
        password: dbPassword,
        database: dbName.trim(),
      })
      setDbTestMessage({ type: 'success', text: t.dbTestSuccess })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t.dbTestConnectFailed
      setDbTestMessage({ type: 'error', text: `${t.dbTestFailedPrefix}${msg}` })
    } finally {
      setTestingDb(false)
    }
  }

  const handleInit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitError('')

    if (!dbHost || !dbUser || !dbName) {
      setSubmitError(t.errFillDbConfig)
      return
    }
    if (!adminUsername || !adminEmail || !adminPassword) {
      setSubmitError(t.errFillAdminInfo)
      return
    }
    if (adminPassword.length < 6) {
      setSubmitError(t.errAdminPasswordMin6)
      return
    }

    setSubmitting(true)
    try {
      const res = await initSetup({
        db: {
          host: dbHost.trim(),
          port: parseInt(dbPort.trim(), 10) || 5432,
          user: dbUser.trim(),
          password: dbPassword,
          database: dbName.trim(),
        },
        admin: {
          username: adminUsername.trim(),
          email: adminEmail.trim(),
          password: adminPassword,
        },
        features: {
          refresh: featureRefresh,
          captcha: featureCaptcha,
          self_delete: featureSelfDelete,
          two_factor_email: featureTwoFactorEmail,
          require_approval: featureRequireApproval,
          two_factor: true,
          logout: true,
          audit_log: true,
          role_change: true,
          session_mode: 'stateless',
          captcha_fail_threshold: 3,
        },
        mail_mode: mailMode,
      })

      if (res.initialized) {
        setInitialized(true)
        navigate('/login', {
          state: {
            message: t.setupInitSuccess
              .replace('{username}', res.admin.username)
              .replace('{email}', res.admin.email),
          },
        })
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t.setupInitFailed
      setSubmitError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="demo-page-container">
      <div className="demo-card demo-setup-card">
        <div className="demo-setup-header">
          <h2>{t.setupHeadingRocket}</h2>
          <p className="demo-muted">
            {t.setupDescReact}
          </p>
        </div>

        <form onSubmit={handleInit} className="demo-setup-form">
          {/* Step 1: PostgreSQL Settings */}
          <section className="demo-form-section">
            <div className="demo-section-title">
              <span className="demo-step-num">1</span>
              <h3>PostgreSQL 数据库配置</h3>
            </div>
            <div className="demo-form-grid">
              <label className="demo-label">
                <span>主机 (Host)</span>
                <input
                  type="text"
                  className="ak-input"
                  value={dbHost}
                  onChange={(e) => setDbHost(e.target.value)}
                  placeholder="127.0.0.1"
                  required
                />
              </label>

              <label className="demo-label">
                <span>端口 (Port)</span>
                <input
                  type="number"
                  className="ak-input"
                  value={dbPort}
                  onChange={(e) => setDbPort(e.target.value)}
                  placeholder="5432"
                  required
                />
              </label>

              <label className="demo-label">
                <span>用户名 (User)</span>
                <input
                  type="text"
                  className="ak-input"
                  value={dbUser}
                  onChange={(e) => setDbUser(e.target.value)}
                  placeholder="postgres"
                  required
                />
              </label>

              <label className="demo-label">
                <span>密码 (Password)</span>
                <input
                  type="password"
                  className="ak-input"
                  value={dbPassword}
                  onChange={(e) => setDbPassword(e.target.value)}
                  placeholder="postgres"
                />
              </label>

              <label className="demo-label full-width">
                <span>数据库名称 (Database)</span>
                <input
                  type="text"
                  className="ak-input"
                  value={dbName}
                  onChange={(e) => setDbName(e.target.value)}
                  placeholder="akdemo"
                  required
                />
              </label>
            </div>

            <div className="demo-db-test-row">
              <button
                type="button"
                className="ak-btn ak-btn-outline"
                onClick={handleTestDb}
                disabled={testingDb}
              >
                {testingDb ? '测试连接中…' : '测试数据库连接'}
              </button>
              {dbTestMessage && (
                <span
                  className={
                    dbTestMessage.type === 'success'
                      ? 'demo-test-success'
                      : 'demo-test-error'
                  }
                >
                  {dbTestMessage.text}
                </span>
              )}
            </div>
          </section>

          {/* Step 2: Admin Account */}
          <section className="demo-form-section">
            <div className="demo-section-title">
              <span className="demo-step-num">2</span>
              <h3>超级管理员账号</h3>
            </div>
            <div className="demo-form-grid">
              <label className="demo-label">
                <span>管理员用户名</span>
                <input
                  type="text"
                  className="ak-input"
                  value={adminUsername}
                  onChange={(e) => setAdminUsername(e.target.value)}
                  placeholder="demo-admin"
                  required
                />
              </label>

              <label className="demo-label">
                <span>管理员邮箱</span>
                <input
                  type="email"
                  className="ak-input"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  placeholder="admin@example.com"
                  required
                />
              </label>

              <label className="demo-label full-width">
                <span>管理员密码 (至少 6 位)</span>
                <input
                  type="password"
                  className="ak-input"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
              </label>
            </div>
          </section>

          {/* Step 3: Feature Toggles */}
          <section className="demo-form-section">
            <div className="demo-section-title">
              <span className="demo-step-num">3</span>
              <h3>功能特性开关</h3>
            </div>
            <div className="demo-checkbox-group">
              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureRefresh}
                  onChange={(e) => setFeatureRefresh(e.target.checked)}
                />
                <div>
                  <strong>刷新令牌 (Refresh Token)</strong>
                  <p>开启轮换式长效会话刷新能力</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureCaptcha}
                  onChange={(e) => setFeatureCaptcha(e.target.checked)}
                />
                <div>
                  <strong>图形验证码 (Captcha)</strong>
                  <p>多次登录失败后触发图形防爆破验证码</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureSelfDelete}
                  onChange={(e) => setFeatureSelfDelete(e.target.checked)}
                />
                <div>
                  <strong>自助注销 (Self Delete)</strong>
                  <p>允许普通用户在个人中心注销账号</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureTwoFactorEmail}
                  onChange={(e) => setFeatureTwoFactorEmail(e.target.checked)}
                />
                <div>
                  <strong>邮箱两步验证 (Two Factor Email)</strong>
                  <p>支持通过邮箱验证码替代 TOTP 验证器完成 2FA</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureRequireApproval}
                  onChange={(e) => setFeatureRequireApproval(e.target.checked)}
                />
                <div>
                  <strong>注册审批 (Require Approval)</strong>
                  <p>新注册账号需管理员审批后方可登录</p>
                </div>
              </label>
            </div>
          </section>

          {/* Step 4: Mail Mode */}
          <section className="demo-form-section">
            <div className="demo-section-title">
              <span className="demo-step-num">4</span>
              <h3>邮件发送模式</h3>
            </div>
            <div className="demo-radio-box selected">
              <input type="radio" checked readOnly />
              <div>
                <strong>Console（控制台 + 站内信箱）</strong>
                <p>
                  Demo 环境推荐模式，所有验证码直接打印到终端及前端「站内信箱」，无需配置
                  SMTP。
                </p>
              </div>
            </div>
          </section>

          {submitError && <div className="ak-error demo-error-box">{submitError}</div>}

          <div className="demo-submit-row">
            <button
              type="submit"
              className="ak-btn ak-btn-primary demo-btn-lg"
              disabled={submitting}
            >
              {submitting ? '正在初始化系统…' : '提交并完成初始化'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
