import React, { useEffect, useState, useCallback, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { getOutbox } from '../lib/api'
import type { OutboxItem } from '../types'

export function translatePurpose(purpose: string): { label: string; color: string } {
  switch (purpose) {
    case 'register':
      return { label: '用户注册', color: '#1677ff' }
    case 'reset_password':
      return { label: '找回密码', color: '#fa8c16' }
    case 'change_password':
      return { label: '修改密码', color: '#722ed1' }
    case 'change_email':
      return { label: '修改邮箱', color: '#13c2c2' }
    case 'login_2fa':
      return { label: '2FA 登录', color: '#eb2f96' }
    case 'disable_2fa':
      return { label: '关闭 2FA', color: '#f5222d' }
    case 'delete_account':
      return { label: '注销账号', color: '#a8071a' }
    default:
      return { label: purpose, color: '#595959' }
  }
}

export const OutboxDrawer: React.FC = () => {
  const { outboxDrawerOpen, setOutboxDrawerOpen } = useAuth()
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
            <span>📬 站内信箱</span>
            <span className="demo-drawer-count">{items.length} 条记录</span>
          </div>
          <div className="demo-drawer-actions">
            <label className="demo-toggle-label" title="每 3 秒刷新一次">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <span>自动刷新</span>
            </label>
            <button
              type="button"
              className="demo-btn-sm"
              onClick={fetchItems}
              disabled={loading}
            >
              {loading ? '刷新中…' : '刷新'}
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
            💡 本地演示模式（console
            邮件）下，所有验证码均在内存信箱中查看，点击下方验证码即可一键复制。
          </p>

          {items.length === 0 ? (
            <div className="demo-empty">信箱暂无验证码记录</div>
          ) : (
            <div className="demo-outbox-list">
              {items.map((item, idx) => {
                const badge = translatePurpose(item.purpose)
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
                        {new Date(item.at).toLocaleTimeString('zh-CN')}
                      </span>
                    </div>

                    <div className="demo-outbox-card-middle">
                      <span className="demo-outbox-code">{item.code}</span>
                      <button
                        type="button"
                        className={`demo-btn-copy ${isCopied ? 'copied' : ''}`}
                        onClick={() => copyCode(item.code)}
                      >
                        {isCopied ? '已复制 ✓' : '复制'}
                      </button>
                    </div>

                    <div className="demo-outbox-card-bottom">
                      <span className="demo-outbox-to" title={item.to}>
                        收件人: {item.to}
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
