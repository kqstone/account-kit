import React, { useEffect, useState, useCallback, useRef } from 'react'
import { getOutbox } from '../lib/api'
import type { OutboxItem } from '../types'
import { translatePurpose } from '../components/OutboxDrawer'

export const OutboxPage: React.FC = () => {
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
            <h2>📬 站内信箱 (Demo Outbox)</h2>
            <p className="demo-muted">
              Demo 环境未配置外部 SMTP 服务器时，发送的所有验证码邮件均由宿主捕获至内存信箱。
            </p>
          </div>

          <div className="demo-outbox-page-controls">
            <label className="demo-toggle-label">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <span>自动刷新 (3s)</span>
            </label>
            <button
              type="button"
              className="ak-btn ak-btn-outline"
              onClick={fetchItems}
              disabled={loading}
            >
              {loading ? '刷新中…' : '立即刷新'}
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="demo-filter-bar" style={{ marginTop: 16 }}>
          <div className="demo-filter-item">
            <label>按收件邮箱过滤</label>
            <input
              type="email"
              className="ak-input"
              placeholder="例如 user@example.com"
              value={filterEmail}
              onChange={(e) => setFilterEmail(e.target.value)}
            />
          </div>

          <div className="demo-filter-item">
            <label>按验证码用途过滤</label>
            <select
              className="ak-input"
              value={filterPurpose}
              onChange={(e) => setFilterPurpose(e.target.value)}
            >
              <option value="">全部用途</option>
              <option value="register">用户注册 (register)</option>
              <option value="reset_password">找回密码 (reset_password)</option>
              <option value="change_password">修改密码 (change_password)</option>
              <option value="change_email">修改邮箱 (change_email)</option>
              <option value="login_2fa">2FA 登录 (login_2fa)</option>
              <option value="disable_2fa">关闭 2FA (disable_2fa)</option>
              <option value="delete_account">注销账号 (delete_account)</option>
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
              重置筛选
            </button>
          </div>
        </div>

        {/* Items List */}
        {loading && items.length === 0 ? (
          <div className="demo-loading-block">正在加载信箱记录…</div>
        ) : items.length === 0 ? (
          <div className="demo-empty">
            信箱为空。触发注册、找回密码或改密/改邮后，验证码将实时出现在这里。
          </div>
        ) : (
          <div className="demo-outbox-grid">
            {items.map((item, index) => {
              const badge = translatePurpose(item.purpose)
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
                      {new Date(item.at).toLocaleString('zh-CN')}
                    </span>
                  </div>

                  <div className="demo-outbox-card-middle">
                    <span className="demo-outbox-code">{item.code}</span>
                    <button
                      type="button"
                      className={`demo-btn-copy ${isCopied ? 'copied' : ''}`}
                      onClick={() => copyCode(item.code)}
                    >
                      {isCopied ? '已复制 ✓' : '复制验证码'}
                    </button>
                  </div>

                  <div className="demo-outbox-card-bottom">
                    <div className="demo-outbox-to">
                      <strong>收件人:</strong> {item.to}
                    </div>
                    <div className="demo-sub-text">语言: {item.language}</div>
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
