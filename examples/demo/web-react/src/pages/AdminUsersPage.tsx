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

export const AdminUsersPage: React.FC = () => {
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
      const msg = err instanceof Error ? err.message : '加载用户列表失败'
      setActionMessage({ type: 'error', text: msg })
    } finally {
      setLoading(false)
    }
  }, [])

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
      notify('success', `用户 ${user.username} 审批状态已更新为: ${status}`)
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusyId(null)
    }
  }

  const handleToggleActive = async (user: AdminUserItem) => {
    setBusyId(user.id)
    try {
      const nextActive = !user.is_active
      await adminPatchUser(user.id, { is_active: nextActive })
      notify('success', `用户 ${user.username} 已${nextActive ? '启用' : '禁用'}`)
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusyId(null)
    }
  }

  const handleReset2Fa = async (user: AdminUserItem) => {
    if (!window.confirm(`确定要为用户 ${user.username} 重置两步验证 (2FA) 吗？这将吊销该用户所有刷新令牌。`)) {
      return
    }
    setBusyId(user.id)
    try {
      await adminReset2Fa(user.id)
      notify('success', `已成功重置 ${user.username} 的两步验证`)
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : '重置 2FA 失败')
    } finally {
      setBusyId(null)
    }
  }

  const handleDeleteUser = async (user: AdminUserItem) => {
    if (!window.confirm(`危险操作！确定要删除用户「${user.username}」吗？`)) {
      return
    }
    setBusyId(user.id)
    try {
      await adminDeleteUser(user.id)
      notify('success', `用户 ${user.username} 已被删除`)
      await loadUsers()
    } catch (err: unknown) {
      notify('error', err instanceof Error ? err.message : '删除用户失败')
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
            👥 用户管理
          </Link>
          <Link to="/admin/audit" className="demo-admin-tab">
            📋 审计日志
          </Link>
        </div>
        <button
          type="button"
          className="ak-btn ak-btn-outline"
          onClick={loadUsers}
          disabled={loading}
        >
          {loading ? '刷新中…' : '刷新列表'}
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
            placeholder="按用户名 / 邮箱 / 姓名搜索…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <span className="demo-muted">共 {filteredUsers.length} 位用户</span>
        </div>

        {loading && users.length === 0 ? (
          <div className="demo-loading-block">正在加载用户列表…</div>
        ) : filteredUsers.length === 0 ? (
          <div className="demo-empty">没有匹配的用户记录</div>
        ) : (
          <div className="demo-table-wrapper">
            <table className="demo-table">
              <thead>
                <tr>
                  <th>用户名</th>
                  <th>邮箱</th>
                  <th>角色/等级</th>
                  <th>权限</th>
                  <th>状态</th>
                  <th>审批状态</th>
                  <th style={{ textAlign: 'right' }}>管理操作</th>
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
                          <span className="demo-tag demo-tag-purple">管理员</span>
                        ) : (
                          <span className="demo-tag demo-tag-gray">普通用户</span>
                        )}
                      </td>
                      <td>
                        {u.is_active ? (
                          <span className="demo-tag demo-tag-green">正常</span>
                        ) : (
                          <span className="demo-tag demo-tag-red">已禁用</span>
                        )}
                      </td>
                      <td>
                        {u.approval_status === 'approved' ? (
                          <span className="demo-tag demo-tag-green">已通过</span>
                        ) : u.approval_status === 'pending' ? (
                          <span className="demo-tag demo-tag-orange">待审批</span>
                        ) : (
                          <span className="demo-tag demo-tag-red">已拒绝</span>
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
                              title="审批通过"
                            >
                              通过
                            </button>
                          ) : !u.is_admin && u.approval_status === 'approved' ? (
                            <button
                              type="button"
                              className="demo-btn-action"
                              disabled={isBusy}
                              onClick={() => handleToggleApproval(u, 'pending')}
                              title="重设为待审"
                            >
                              重设待审
                            </button>
                          ) : null}
                          {!u.is_admin && u.approval_status === 'pending' && (
                            <button
                              type="button"
                              className="demo-btn-action demo-btn-action-red"
                              disabled={isBusy}
                              onClick={() => handleToggleApproval(u, 'rejected')}
                              title="拒绝审批"
                            >
                              拒绝
                            </button>
                          )}

                          {!u.is_admin && (
                            <button
                              type="button"
                              className="demo-btn-action"
                              disabled={isBusy}
                              onClick={() => handleToggleActive(u)}
                            >
                              {u.is_active ? '禁用' : '启用'}
                            </button>
                          )}

                          {/* Reset 2FA */}
                          <button
                            type="button"
                            className="demo-btn-action"
                            disabled={isBusy}
                            onClick={() => handleReset2Fa(u)}
                            title="重置用户两步验证"
                          >
                            重置 2FA
                          </button>

                          {!u.is_admin && (
                            <button
                              type="button"
                              className="demo-btn-action demo-btn-action-red"
                              disabled={isBusy}
                              onClick={() => handleDeleteUser(u)}
                              title="删除该用户"
                            >
                              删除
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
