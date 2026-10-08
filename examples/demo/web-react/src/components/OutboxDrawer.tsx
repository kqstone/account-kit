import React, { useEffect, useState, useCallback, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { getOutbox } from '../lib/api'
import { useDemoI18n, readDemoLocale, demoMessages, type DemoMessages } from '../lib/i18n'
import type { OutboxItem } from '../types'

export function translatePurpose(purpose: string, t?: DemoMessages): { label: string; color: string } {
  const msgs = t || demoMessages[readDemoLocale()]
  switch (purpose) {
    case 'register':
      return { label: msgs.purposeRegister, color: '#1677ff' }
    case 'reset_password':
      return { label: msgs.purposeResetPassword, color: '#fa8c16' }
    case 'change_password':
      return { label: msgs.purposeChangePassword, color: '#722ed1' }
    case 'change_email':
      return { label: msgs.purposeChangeEmail, color: '#13c2c2' }
    case 'login_2fa':
      return { label: msgs.purposeLogin2fa, color: '#eb2f96' }
    case 'disable_2fa':
      return { label: msgs.purposeDisable2fa, color: '#f5222d' }
    case 'delete_account':
      return { label: msgs.purposeDeleteAccount, color: '#a8071a' }
    default:
      return { label: purpose, color: '#595959' }
  }
}

export const OutboxDrawer: React.FC = () => {
  const { outboxDrawerOpen, setOutboxDrawerOpen } = useAuth()
  const { locale, t } = useDemoI18n()
  const dateLocale = locale === 'zh-CN' ? 'zh-CN' : 'en-US'
  const [items, setItems] = useState<OutboxItem[]>([])
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [copiedCode, setCopiedCode] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchItems = useCallback(async () => {
    try {
      setLoading(true)
      const data = await getOutbox()
      setItems(data.items || [])
    } catch (err) {
      console.warn('Outbox fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (outboxDrawerOpen) {
      void fetchItems()
    }
  }, [outboxDrawerOpen, fetchItems])

  useEffect(() => {
    if (outboxDrawerOpen && autoRefresh) {
      timerRef.current = setInterval(() => {
        void fetchItems()
      }, 3000)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [outboxDrawerOpen, autoRefresh, fetchItems])

  const copyCode = (code: string) => {
    void navigator.clipboard?.writeText(code)
    setCopiedCode(code)
    setTimeout(() => setCopiedCode(null), 1500)
  }

  if (!outboxDrawerOpen) return null

  return (
    <aside className="demo-drawer-overlay" onClick={() => setOutboxDrawerOpen(false)}>
      <div className="demo-drawer-panel" onClick={(e) => e.stopPropagation()}>
        <div className="demo-drawer-header">
          <div className="demo-drawer-title">
            <span>{t.outboxTitle}</span>
            <span className="demo-drawer-count">{t.recordCount.replace('{count}', String(items.length))}</span>
          </div>
          <div className="demo-drawer-actions">
            <label className="demo-toggle-label" title={t.autoRefreshTip}>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <span>{t.autoRefreshLabel}</span>
            </label>
            <button
              type="button"
              className="demo-btn-sm"
              onClick={fetchItems}
              disabled={loading}
            >
              {loading ? t.refreshingBtn : t.refreshBtn}
            </button>
            <button
              type="button"
              className="demo-drawer-close"
              onClick={() => setOutboxDrawerOpen(false)}
            >
              ✕
            </button>
          </div>
        </div>

        <div className="demo-drawer-body">
          <p className="demo-drawer-tip">
            {t.outboxDrawerTip}
          </p>

          {items.length === 0 ? (
            <div className="demo-empty">{t.outboxEmptyDrawer}</div>
          ) : (
            <div className="demo-outbox-list">
              {items.map((item, idx) => {
                const badge = translatePurpose(item.purpose, t)
                const isCopied = copiedCode === item.code
                return (
                  <div key={`${item.at}-${idx}`} className="demo-outbox-card">
                    <div className="demo-outbox-card-top">
                      <span
                        className="demo-purpose-badge"
                        style={{ backgroundColor: badge.color }}
                      >
                        {badge.label}
                      </span>
                      <span className="demo-outbox-time">
                        {new Date(item.at).toLocaleTimeString(dateLocale)}
                      </span>
                    </div>

                    <div className="demo-outbox-card-middle">
                      <span className="demo-outbox-code">{item.code}</span>
                      <button
                        type="button"
                        className={`demo-btn-copy ${isCopied ? 'copied' : ''}`}
                        onClick={() => copyCode(item.code)}
                      >
                        {isCopied ? t.copiedBtn : t.copyBtn}
                      </button>
                    </div>

                    <div className="demo-outbox-card-bottom">
                      <span className="demo-outbox-to" title={item.to}>
                        {t.recipientLabel}: {item.to}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
