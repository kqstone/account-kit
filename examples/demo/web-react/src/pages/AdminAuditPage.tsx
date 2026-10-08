import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { adminGetAuditLogs } from '../lib/api'
import type { AuditLogItem } from '../types'
import { useDemoI18n, type DemoMessages } from '../lib/i18n'

const getEventOptions = (t: DemoMessages) => [
  { value: '', label: t.allEventsReact },
  { value: 'login_success', label: `${t.audit_login_success} (login_success)` },
  { value: 'login_failed', label: `${t.audit_login_failed} (login_failed)` },
  { value: 'login_2fa_failed', label: `${t.audit_login_2fa_failed_short} (login_2fa_failed)` },
  { value: '2fa_enabled', label: `${t.audit_2fa_enabled} (2fa_enabled)` },
  { value: '2fa_disabled', label: `${t.audit_2fa_disabled} (2fa_disabled)` },
  { value: '2fa_reset', label: `${t.audit_2fa_reset} (2fa_reset)` },
  { value: '2fa_recovery_regenerated', label: `${t.audit_2fa_recovery_regenerated_short} (2fa_recovery_regenerated)` },
  { value: 'password_changed', label: `${t.audit_password_changed} (password_changed)` },
  { value: 'password_reset', label: `${t.audit_password_reset} (password_reset)` },
  { value: 'email_changed', label: `${t.audit_email_changed} (email_changed)` },
  { value: 'logout', label: `${t.audit_logout} (logout)` },
  { value: 'refresh_reuse_detected', label: `${t.audit_refresh_reuse_detected_short} (refresh_reuse_detected)` },
  { value: 'account_deleted', label: `${t.audit_account_deleted_short} (account_deleted)` },
  { value: 'verification_code_locked', label: `${t.audit_verification_code_locked} (verification_code_locked)` },
  { value: 'admin_user_updated', label: `${t.audit_admin_user_updated} (admin_user_updated)` },
  { value: 'admin_user_deleted', label: `${t.audit_admin_user_deleted} (admin_user_deleted)` },
  { value: 'admin_role_changed', label: `${t.audit_admin_role_changed} (admin_role_changed)` },
  { value: 'admin_tier_changed', label: `${t.audit_admin_tier_changed} (admin_tier_changed)` },
  { value: 'role_change_reviewed', label: `${t.audit_role_change_reviewed} (role_change_reviewed)` },
]

export const AdminAuditPage: React.FC = () => {
  const { locale, t } = useDemoI18n()
  const dateLocale = locale === 'zh-CN' ? 'zh-CN' : 'en-US'
  const eventOptions = useMemo(() => getEventOptions(t), [t])

  const [logs, setLogs] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedEvent, setSelectedEvent] = useState('')
  const [userIdFilter, setUserIdFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadLogs = useCallback(
    async (targetPage = page) => {
      setLoading(true)
      setError('')
      try {
        const res = await adminGetAuditLogs({
          page: targetPage,
          page_size: pageSize,
          event: selectedEvent || undefined,
          user_id: userIdFilter.trim() || undefined,
        })
        setLogs(res.items || [])
        setTotal(res.total || 0)
        setPage(res.page || targetPage)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : t.loadAuditLogsFailed)
      } finally {
        setLoading(false)
      }
    },
    [page, pageSize, selectedEvent, userIdFilter, t.loadAuditLogsFailed]
  )

  useEffect(() => {
    void loadLogs(1)
  }, [pageSize, selectedEvent]) // reload on filter change

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    void loadLogs(1)
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="demo-page-container">
      {/* Admin Nav Subheader */}
      <div className="demo-admin-header">
        <div className="demo-admin-tabs">
          <Link to="/admin" className="demo-admin-tab">
            {t.tabUsersWithIcon}
          </Link>
          <Link to="/admin/audit" className="demo-admin-tab active">
            {t.tabAuditLogWithIcon}
          </Link>
        </div>
        <button
          type="button"
          className="ak-btn ak-btn-outline"
          onClick={() => void loadLogs(page)}
          disabled={loading}
        >
          {loading ? t.refreshingBtn : t.refreshLogsSimple}
        </button>
      </div>

      {error && <div className="ak-error" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="demo-card">
        {/* Filters */}
        <form onSubmit={handleSearchSubmit} className="demo-filter-bar">
          <div className="demo-filter-item">
            <label>{t.filterEventLabel}</label>
            <select
              className="ak-input"
              value={selectedEvent}
              onChange={(e) => setSelectedEvent(e.target.value)}
            >
              {eventOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="demo-filter-item">
            <label>{t.filterUserIdLabel}</label>
            <input
              type="text"
              className="ak-input"
              placeholder={t.filterUserIdReactPlaceholder}
              value={userIdFilter}
              onChange={(e) => setUserIdFilter(e.target.value)}
            />
          </div>

          <div className="demo-filter-item">
            <label>{t.filterPageSizeLabel}</label>
            <select
              className="ak-input"
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
            >
              <option value={10}>{t.pageSizeOption.replace('{count}', '10')}</option>
              <option value={20}>{t.pageSizeOption.replace('{count}', '20')}</option>
              <option value={50}>{t.pageSizeOption.replace('{count}', '50')}</option>
              <option value={100}>{t.pageSizeOption.replace('{count}', '100')}</option>
            </select>
          </div>

          <div className="demo-filter-item-btn">
            <button type="submit" className="ak-btn ak-btn-primary" disabled={loading}>
              {t.queryBtn}
            </button>
          </div>
        </form>

        {/* Table */}
        {loading && logs.length === 0 ? (
          <div className="demo-loading-block">{t.loadingAuditLogs}</div>
        ) : logs.length === 0 ? (
          <div className="demo-empty">{t.noAuditLogsFoundReact}</div>
        ) : (
          <>
            <div className="demo-table-wrapper">
              <table className="demo-table">
                <thead>
                  <tr>
                    <th>{t.thTime}</th>
                    <th>{t.thEventName}</th>
                    <th>{t.thOperatorUserId}</th>
                    <th>{t.thIpDevice}</th>
                    <th>{t.thMetaSimple}</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {new Date(log.created_at).toLocaleString(dateLocale)}
                      </td>
                      <td>
                        <span className="demo-event-tag">{log.event}</span>
                      </td>
                      <td>
                        {log.user_id ? (
                          <code className="demo-code-inline">{log.user_id}</code>
                        ) : (
                          <span className="demo-muted">{t.systemOrAnonymous}</span>
                        )}
                      </td>
                      <td>
                        <div>{log.ip || '-'}</div>
                        {log.device_name && (
                          <div className="demo-sub-text">{log.device_name}</div>
                        )}
                      </td>
                      <td>
                        {log.meta && Object.keys(log.meta).length > 0 ? (
                          <pre className="demo-meta-json">
                            {JSON.stringify(log.meta, null, 2)}
                          </pre>
                        ) : (
                          <span className="demo-muted">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="demo-pagination">
              <span className="demo-pagination-info">
                {t.paginationTotalText
                  .replace('{total}', String(total))
                  .replace('{page}', String(page))
                  .replace('{totalPages}', String(totalPages))}
              </span>
              <div className="demo-pagination-btns">
                <button
                  type="button"
                  className="demo-btn-sm"
                  disabled={page <= 1 || loading}
                  onClick={() => void loadLogs(page - 1)}
                >
                  {t.prevPageBtn}
                </button>
                <button
                  type="button"
                  className="demo-btn-sm"
                  disabled={page >= totalPages || loading}
                  onClick={() => void loadLogs(page + 1)}
                >
                  {t.nextPageBtn}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
