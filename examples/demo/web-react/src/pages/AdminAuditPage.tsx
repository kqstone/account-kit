import React, { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { adminGetAuditLogs } from '../lib/api'
import type { AuditLogItem } from '../types'

const EVENT_OPTIONS = [
  { value: '', label: '全部事件' },
  { value: 'login_success', label: '登录成功 (login_success)' },
  { value: 'login_failed', label: '登录失败 (login_failed)' },
  { value: 'login_2fa_failed', label: '2FA 失败 (login_2fa_failed)' },
  { value: '2fa_enabled', label: '开启 2FA (2fa_enabled)' },
  { value: '2fa_disabled', label: '关闭 2FA (2fa_disabled)' },
  { value: '2fa_reset', label: '重置 2FA (2fa_reset)' },
  { value: '2fa_recovery_regenerated', label: '重置恢复码 (2fa_recovery_regenerated)' },
  { value: 'password_changed', label: '修改密码 (password_changed)' },
  { value: 'password_reset', label: '重置密码 (password_reset)' },
  { value: 'email_changed', label: '修改邮箱 (email_changed)' },
  { value: 'logout', label: '退出登录 (logout)' },
  { value: 'refresh_reuse_detected', label: '刷新令牌重用 (refresh_reuse_detected)' },
  { value: 'account_deleted', label: '注销账号 (account_deleted)' },
  { value: 'verification_code_locked', label: '验证码锁定 (verification_code_locked)' },
  { value: 'admin_user_updated', label: '管理员更新用户 (admin_user_updated)' },
  { value: 'admin_user_deleted', label: '管理员删除用户 (admin_user_deleted)' },
  { value: 'admin_role_changed', label: '管理员修改角色 (admin_role_changed)' },
  { value: 'admin_tier_changed', label: '管理员修改等级 (admin_tier_changed)' },
  { value: 'role_change_reviewed', label: '角色申请审核 (role_change_reviewed)' },
]

export const AdminAuditPage: React.FC = () => {
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
        setError(err instanceof Error ? err.message : '加载审计日志失败')
      } finally {
        setLoading(false)
      }
    },
    [page, pageSize, selectedEvent, userIdFilter]
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
            👥 用户管理
          </Link>
          <Link to="/admin/audit" className="demo-admin-tab active">
            📋 审计日志
          </Link>
        </div>
        <button
          type="button"
          className="ak-btn ak-btn-outline"
          onClick={() => void loadLogs(page)}
          disabled={loading}
        >
          {loading ? '刷新中…' : '刷新日志'}
        </button>
      </div>

      {error && <div className="ak-error" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="demo-card">
        {/* Filters */}
        <form onSubmit={handleSearchSubmit} className="demo-filter-bar">
          <div className="demo-filter-item">
            <label>事件过滤</label>
            <select
              className="ak-input"
              value={selectedEvent}
              onChange={(e) => setSelectedEvent(e.target.value)}
            >
              {EVENT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="demo-filter-item">
            <label>用户 ID (UUID)</label>
            <input
              type="text"
              className="ak-input"
              placeholder="可选精确过滤 user_id"
              value={userIdFilter}
              onChange={(e) => setUserIdFilter(e.target.value)}
            />
          </div>

          <div className="demo-filter-item">
            <label>每页条数</label>
            <select
              className="ak-input"
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
            >
              <option value={10}>10 条 / 页</option>
              <option value={20}>20 条 / 页</option>
              <option value={50}>50 条 / 页</option>
              <option value={100}>100 条 / 页</option>
            </select>
          </div>

          <div className="demo-filter-item-btn">
            <button type="submit" className="ak-btn ak-btn-primary" disabled={loading}>
              查询
            </button>
          </div>
        </form>

        {/* Table */}
        {loading && logs.length === 0 ? (
          <div className="demo-loading-block">正在加载审计日志…</div>
        ) : logs.length === 0 ? (
          <div className="demo-empty">没有查询到相关审计日志记录</div>
        ) : (
          <>
            <div className="demo-table-wrapper">
              <table className="demo-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>事件名称</th>
                    <th>操作者/用户 ID</th>
                    <th>IP / 设备</th>
                    <th>元数据 (Meta)</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {new Date(log.created_at).toLocaleString('zh-CN')}
                      </td>
                      <td>
                        <span className="demo-event-tag">{log.event}</span>
                      </td>
                      <td>
                        {log.user_id ? (
                          <code className="demo-code-inline">{log.user_id}</code>
                        ) : (
                          <span className="demo-muted">系统 / 匿名</span>
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
                共 {total} 条记录，第 {page} / {totalPages} 页
              </span>
              <div className="demo-pagination-btns">
                <button
                  type="button"
                  className="demo-btn-sm"
                  disabled={page <= 1 || loading}
                  onClick={() => void loadLogs(page - 1)}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="demo-btn-sm"
                  disabled={page >= totalPages || loading}
                  onClick={() => void loadLogs(page + 1)}
                >
                  下一页
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
