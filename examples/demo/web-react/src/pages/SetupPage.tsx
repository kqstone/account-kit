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
  const [dbTestResult, setDbTestResult] = useState<{
    type: 'success' | 'error'
    rawMsg?: string
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
  const [submitError, setSubmitError] = useState<{
    type?: 'db' | 'admin' | 'pwd' | 'initFailed'
    custom?: string
  } | null>(null)

  const handleTestDb = async () => {
    setTestingDb(true)
    setDbTestResult(null)
    try {
      await testDatabase({
        host: dbHost.trim(),
        port: parseInt(dbPort.trim(), 10) || 5432,
        user: dbUser.trim(),
        password: dbPassword,
        database: dbName.trim(),
      })
      setDbTestResult({ type: 'success' })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      setDbTestResult({ type: 'error', rawMsg: msg })
    } finally {
      setTestingDb(false)
    }
  }

  const handleInit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitError(null)

    if (!dbHost || !dbUser || !dbName) {
      setSubmitError({ type: 'db' })
      return
    }
    if (!adminUsername || !adminEmail || !adminPassword) {
      setSubmitError({ type: 'admin' })
      return
    }
    if (adminPassword.length < 6) {
      setSubmitError({ type: 'pwd' })
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
      const msg = err instanceof Error && err.message ? err.message : ''
      setSubmitError(msg ? { custom: msg } : { type: 'initFailed' })
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
              <h3>{t.sec1DbReact}</h3>
            </div>
            <div className="demo-form-grid">
              <label className="demo-label">
                <span>{t.dbHost}</span>
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
                <span>{t.dbPort}</span>
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
                <span>{t.dbUser}</span>
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
                <span>{t.dbPassword}</span>
                <input
                  type="password"
                  className="ak-input"
                  value={dbPassword}
                  onChange={(e) => setDbPassword(e.target.value)}
                  placeholder="postgres"
                />
              </label>

              <label className="demo-label full-width">
                <span>{t.dbNameReact}</span>
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
                {testingDb ? t.testingDb : t.btnTestDb}
              </button>
              {dbTestResult && (
                <span
                  className={
                    dbTestResult.type === 'success'
                      ? 'demo-test-success'
                      : 'demo-test-error'
                  }
                >
                  {dbTestResult.type === 'success'
                    ? t.dbTestSuccess
                    : `${t.dbTestFailedPrefix}${dbTestResult.rawMsg || t.dbTestConnectFailed}`}
                </span>
              )}
            </div>
          </section>

          {/* Step 2: Admin Account */}
          <section className="demo-form-section">
            <div className="demo-section-title">
              <span className="demo-step-num">2</span>
              <h3>{t.sec2AdminReact}</h3>
            </div>
            <div className="demo-form-grid">
              <label className="demo-label">
                <span>{t.adminUsername}</span>
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
                <span>{t.adminEmail}</span>
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
                <span>{t.adminPassword}</span>
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
              <h3>{t.sec3FeaturesReact}</h3>
            </div>
            <div className="demo-checkbox-group">
              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureRefresh}
                  onChange={(e) => setFeatureRefresh(e.target.checked)}
                />
                <div>
                  <strong>{t.featRefreshReact}</strong>
                  <p>{t.featRefreshDescReact}</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureCaptcha}
                  onChange={(e) => setFeatureCaptcha(e.target.checked)}
                />
                <div>
                  <strong>{t.featCaptchaReact}</strong>
                  <p>{t.featCaptchaDescReact}</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureSelfDelete}
                  onChange={(e) => setFeatureSelfDelete(e.target.checked)}
                />
                <div>
                  <strong>{t.featSelfDeleteReact}</strong>
                  <p>{t.featSelfDeleteDescReact}</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureTwoFactorEmail}
                  onChange={(e) => setFeatureTwoFactorEmail(e.target.checked)}
                />
                <div>
                  <strong>{t.featTwoFactorEmailReact}</strong>
                  <p>{t.featTwoFactorEmailDescReact}</p>
                </div>
              </label>

              <label className="demo-checkbox-card">
                <input
                  type="checkbox"
                  checked={featureRequireApproval}
                  onChange={(e) => setFeatureRequireApproval(e.target.checked)}
                />
                <div>
                  <strong>{t.featRequireApprovalReact}</strong>
                  <p>{t.featRequireApprovalDescReact}</p>
                </div>
              </label>
            </div>
          </section>

          {/* Step 4: Mail Mode */}
          <section className="demo-form-section">
            <div className="demo-section-title">
              <span className="demo-step-num">4</span>
              <h3>{t.sec4MailReact}</h3>
            </div>
            <div className="demo-radio-box selected">
              <input type="radio" checked readOnly />
              <div>
                <strong>{t.mailConsoleReactTitle}</strong>
                <p>{t.mailConsoleReactDesc}</p>
              </div>
            </div>
          </section>

          {submitError && (
            <div className="ak-error demo-error-box">
              {submitError.custom ||
                (submitError.type === 'db'
                  ? t.errFillDbConfig
                  : submitError.type === 'admin'
                  ? t.errFillAdminInfo
                  : submitError.type === 'pwd'
                  ? t.errAdminPasswordMin6
                  : t.setupInitFailed)}
            </div>
          )}

          <div className="demo-submit-row">
            <button
              type="submit"
              className="ak-btn ak-btn-primary demo-btn-lg"
              disabled={submitting}
            >
              {submitting ? t.submittingSetup : t.submitAndInitBtn}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
