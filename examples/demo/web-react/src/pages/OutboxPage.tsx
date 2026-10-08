import React, { useEffect, useState, useCallback, useRef } from 'react'
import { getOutbox } from '../lib/api'
import type { OutboxItem } from '../types'
import { translatePurpose } from '../components/OutboxDrawer'
import { useDemoI18n } from '../lib/i18n'

export const OutboxPage: React.FC = () => {
  const { locale, t } = useDemoI18n()
  const dateLocale = locale === 'zh-CN' ? 'zh-CN' : 'en-US'
  const [items, setItems] = useState<OutboxItem[]>([])
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [filterEmail, setFilterEmail] = useState('')
  const [filterPurpose, setFilterPurpose] = useState('')
  const [copiedCode, setCopiedCode] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchItems = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getOutbox(
        filterEmail.trim() || undefined,
        filterPurpose || undefined
      )
      setItems(data.items || [])
    } catch (err) {
      console.warn('Failed to load outbox:', err)
    } finally {
      setLoading(false)
    }
  }, [filterEmail, filterPurpose])

  useEffect(() => {
    void fetchItems()
  }, [fetchItems])

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(() => {
        void fetchItems()
      }, 3000)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [autoRefresh, fetchItems])

  const copyCode = (code: string) => {
    void navigator.clipboard?.writeText(code)
    setCopiedCode(code)
    setTimeout(() => setCopiedCode(null), 1500)
  }

  return (
    <div className="demo-page-container">
      <div className="demo-card">
        <div className="demo-outbox-page-header">
          <div>
            <h2>{t.outboxPageTitle}</h2>
            <p className="demo-muted">
              {t.outboxPageDesc}
            </p>
          </div>

          <div className="demo-outbox-page-controls">
            <label className="demo-toggle-label">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <span>{t.autoRefresh}</span>
            </label>
            <button
              type="button"
              className="ak-btn ak-btn-outline"
              onClick={fetchItems}
              disabled={loading}
            >
              {loading ? t.refreshingBtn : t.refreshBtnNow}
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="demo-filter-bar" style={{ marginTop: 16 }}>
          <div className="demo-filter-item">
            <label>{t.filterRecipientLabel}</label>
            <input
              type="email"
              className="ak-input"
              placeholder={t.filterRecipientPlaceholder}
              value={filterEmail}
              onChange={(e) => setFilterEmail(e.target.value)}
            />
          </div>

          <div className="demo-filter-item">
            <label>{t.filterPurposeLabel}</label>
            <select
              className="ak-input"
              value={filterPurpose}
              onChange={(e) => setFilterPurpose(e.target.value)}
            >
              <option value="">{t.purposeAll}</option>
              <option value="register">{t.purposeOptRegister}</option>
              <option value="reset_password">{t.purposeOptResetPassword}</option>
              <option value="change_password">{t.purposeOptChangePassword}</option>
              <option value="change_email">{t.purposeOptChangeEmail}</option>
              <option value="login_2fa">{t.purposeOptLogin2fa}</option>
              <option value="disable_2fa">{t.purposeOptDisable2fa}</option>
              <option value="delete_account">{t.purposeOptDeleteAccount}</option>
            </select>
          </div>

          <div className="demo-filter-item-btn">
            <button
              type="button"
              className="ak-btn ak-btn-outline"
              onClick={() => {
                setFilterEmail('')
                setFilterPurpose('')
              }}
            >
              {t.resetFilterBtn}
            </button>
          </div>
        </div>

        {/* Items List */}
        {loading && items.length === 0 ? (
          <div className="demo-loading-block">{t.loadingOutboxRecords}</div>
        ) : items.length === 0 ? (
          <div className="demo-empty">
            {t.outboxEmptyPage}
          </div>
        ) : (
          <div className="demo-outbox-grid">
            {items.map((item, index) => {
              const badge = translatePurpose(item.purpose, t)
              const isCopied = copiedCode === item.code
              return (
                <div key={`${item.at}-${index}`} className="demo-outbox-card">
                  <div className="demo-outbox-card-top">
                    <span
                      className="demo-purpose-badge"
                      style={{ backgroundColor: badge.color }}
                    >
                      {badge.label}
                    </span>
                    <span className="demo-outbox-time">
                      {new Date(item.at).toLocaleString(dateLocale)}
                    </span>
                  </div>

                  <div className="demo-outbox-card-middle">
                    <span className="demo-outbox-code">{item.code}</span>
                    <button
                      type="button"
                      className={`demo-btn-copy ${isCopied ? 'copied' : ''}`}
                      onClick={() => copyCode(item.code)}
                    >
                      {isCopied ? t.copiedBtn : t.copyCodeBtn}
                    </button>
                  </div>

                  <div className="demo-outbox-card-bottom">
                    <div className="demo-outbox-to">
                      <strong>{t.recipientLabel}:</strong> {item.to}
                    </div>
                    <div className="demo-sub-text">{t.languageLabel}: {item.language}</div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
