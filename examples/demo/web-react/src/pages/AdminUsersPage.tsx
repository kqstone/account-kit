import React, { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  adminDeleteUser,
  adminGetUsers,
  adminPatchUser,
  adminReset2Fa,
} from '../lib/api'
import type { AdminUserItem } from '../types'
import { TierBadge } from '@kqstone/account-ui-react'
import { useDemoI18n } from '../lib/i18n'

export const AdminUsersPage: React.FC = () => {
  const { t } = useDemoI18n()
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [loading, setLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [actionMessage, setActionMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const data = await adminGetUsers()
      setUsers(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t.loadUsersFailed
      setActionMessage({ type: 'error', text: msg })
    } finally {
      setLoading(false)
    }
  }, [t.loadUsersFailed])

  useEffect(() => {
    void loadUsers()
  }, [loadUsers])

  const notify = (type: 'success' | 'error', text: string) => {
    setActionMessage({ type, text })
    setTimeout(() => setActionMessage(null), 4000)
  }

  const handleToggleApproval = async (
    user: AdminUserItem,
    status: 'approved' | 'rejected' | 'pending'
  ) => {
    setBusyId(user.id)
    try {
      await adminPatchUser(user.id, { approval_status: status })
      notify('success', t.userApprovalStatusUpdated.replace('{username}', user.username).replace('{status}', status))
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : t.opFailed)
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleActive = async (user: AdminUserItem) => {
    setBusyId(user.id)
    try {
      const nextActive = !user.is_active
      await adminPatchUser(user.id, { is_active: nextActive })
      notify(
        'success',
        t.userStatusUpdated
          .replace('{username}', user.username)
          .replace('{action}', nextActive ? t.actionEnabled : t.actionDeactivated)
      )
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : t.opFailed)
    } finally {
      setBusyId(null)
    }
  }

  const handleReset2Fa = async (user: AdminUserItem) => {
    if (!window.confirm(t.confirmReset2faReact.replace('{username}', user.username))) {
      return
    }
    setBusyId(user.id)
    try {
      await adminReset2Fa(user.id)
      notify('success', t.reset2faSuccess.replace('{username}', user.username))
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : t.reset2faFailed)
    } finally {
      setBusyId(null)
    }
  }

  const handleDeleteUser = async (user: AdminUserItem) => {
    if (!window.confirm(t.confirmDeleteUser.replace('{username}', user.username))) {
      return
    }
    setBusyId(user.id)
    try {
      await adminDeleteUser(user.id)
      notify('success', t.deleteUserSuccess.replace('{username}', user.username))
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : t.deleteUserFailed)
    } finally {
      setBusyId(null)
    }
  }

  const filteredUsers = users.filter((u) => {
    const q = searchTerm.trim().toLowerCase()
    if (!q) return true
    return (
      u.username.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.full_name && u.full_name.toLowerCase().includes(q))
    )
  })

  return (
    <div className="demo-page-container">
      {/* Admin Nav Subheader */}
      <div className="demo-admin-header">
        <div className="demo-admin-tabs">
          <Link to="/admin" className="demo-admin-tab active">
            {t.tabUsersWithIcon}
          </Link>
          <Link to="/admin/audit" className="demo-admin-tab">
            {t.tabAuditLogWithIcon}
          </Link>
        </div>
        <button
          type="button"
          className="ak-btn ak-btn-outline"
          onClick={loadUsers}
          disabled={loading}
        >
          {loading ? t.refreshingBtn : t.refreshListBtn}
        </button>
      </div>

      {actionMessage && (
        <div
          className={
            actionMessage.type === 'success' ? 'ak-success' : 'ak-error'
          }
          style={{ marginBottom: 16 }}
        >
          {actionMessage.text}
        </div>
      )}

      <div className="demo-card">
        <div className="demo-table-toolbar">
          <input
            type="text"
            className="ak-input demo-search-input"
            placeholder={t.searchUserReactPlaceholder}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <span className="demo-muted">{t.totalUsersCount.replace('{count}', String(filteredUsers.length))}</span>
        </div>

        {loading && users.length === 0 ? (
          <div className="demo-loading-block">{t.loadingUsersBlock}</div>
        ) : filteredUsers.length === 0 ? (
          <div className="demo-empty">{t.noMatchingUsers}</div>
        ) : (
          <div className="demo-table-wrapper">
            <table className="demo-table">
              <thead>
                <tr>
                  <th>{t.thUsername}</th>
                  <th>{t.thEmail}</th>
                  <th>{t.thRoleAndTier}</th>
                  <th>{t.thPermissions}</th>
                  <th>{t.thStatus}</th>
                  <th>{t.thApprovalStatus}</th>
                  <th style={{ textAlign: 'right' }}>{t.thAdminActions}</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => {
                  const isBusy = busyId === u.id
                  return (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.username}</strong>
                        {u.full_name && (
                          <div className="demo-sub-text">{u.full_name}</div>
                        )}
                      </td>
                      <td>{u.email}</td>
                      <td>
                        <span>{u.role}</span>
                        {u.tier_name && (
                          <span style={{ marginLeft: 6 }}>
                            <TierBadge
                              name={u.tier_name}
                              color={u.tier_badge_color}
                            />
                          </span>
                        )}
                      </td>
                      <td>
                        {u.is_admin ? (
                          <span className="demo-tag demo-tag-purple">{t.roleAdmin}</span>
                        ) : (
                          <span className="demo-tag demo-tag-gray">{t.roleNormal}</span>
                        )}
                      </td>
                      <td>
                        {u.is_active ? (
                          <span className="demo-tag demo-tag-green">{t.statusActive}</span>
                        ) : (
                          <span className="demo-tag demo-tag-red">{t.statusDisabled}</span>
                        )}
                      </td>
                      <td>
                        {u.approval_status === 'approved' ? (
                          <span className="demo-tag demo-tag-green">{t.statusApproved}</span>
                        ) : u.approval_status === 'pending' ? (
                          <span className="demo-tag demo-tag-orange">{t.statusPending}</span>
                        ) : (
                          <span className="demo-tag demo-tag-red">{t.statusRejected}</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div className="demo-action-buttons">
                          {/* Approval Actions */}
                          {!u.is_admin && u.approval_status !== 'approved' ? (
                            <button
                              type="button"
                              className="demo-btn-action demo-btn-action-green"
                              disabled={isBusy}
                              onClick={() => handleToggleApproval(u, 'approved')}
                              title={t.titleApprove}
                            >
                              {t.btnApprove}
                            </button>
                          ) : !u.is_admin && u.approval_status === 'approved' ? (
                            <button
                              type="button"
                              className="demo-btn-action"
                              disabled={isBusy}
                              onClick={() => handleToggleApproval(u, 'pending')}
                              title={t.titleResetPending}
                            >
                              {t.btnResetPending}
                            </button>
                          ) : null}
                          {!u.is_admin && u.approval_status === 'pending' && (
                            <button
                              type="button"
                              className="demo-btn-action demo-btn-action-red"
                              disabled={isBusy}
                              onClick={() => handleToggleApproval(u, 'rejected')}
                              title={t.titleReject}
                            >
                              {t.btnReject}
                            </button>
                          )}

                          {!u.is_admin && (
                            <button
                              type="button"
                              className="demo-btn-action"
                              disabled={isBusy}
                              onClick={() => handleToggleActive(u)}
                            >
                              {u.is_active ? t.btnDisable : t.btnEnable}
                            </button>
                          )}

                          {/* Reset 2FA */}
                          <button
                            type="button"
                            className="demo-btn-action"
                            disabled={isBusy}
                            onClick={() => handleReset2Fa(u)}
                            title={t.titleReset2faReact}
                          >
                            {t.btnReset2fa}
                          </button>

                          {!u.is_admin && (
                            <button
                              type="button"
                              className="demo-btn-action demo-btn-action-red"
                              disabled={isBusy}
                              onClick={() => handleDeleteUser(u)}
                              title={t.titleDelete}
                            >
                              {t.btnDelete}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
