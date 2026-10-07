import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import QRCode from 'qrcode'
import {
  ProfileFields,
  ChangeEmailForm,
  TwoFactorSettings,
  LogoutButton,
  DeleteAccountForm,
  AvatarUploader,
  TierBadge,
  type AccountUser,
  type TwoFactorStatus,
} from '@kqstone/account-ui-react'
import { accountClient, tokenStore } from '../lib/auth'
import { useAuth } from '../context/AuthContext'

export const AccountPage: React.FC = () => {
  const { user, token, refreshUser, logout } = useAuth()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState<
    'profile' | 'email' | '2fa' | 'security'
  >('profile')
  const [twoFactorStatus, setTwoFactorStatus] =
    useState<TwoFactorStatus | null>(null)
  const [infoMessage, setInfoMessage] = useState('')

  // Load 2FA status to feed into DeleteAccountForm
  useEffect(() => {
    if (!token) return
    accountClient
      .twoFactorStatus(token)
      .then((st) => setTwoFactorStatus(st))
      .catch((err) => console.warn('Could not load 2FA status:', err))
  }, [token])

  if (!token || !user) {
    return (
      <div className="demo-page-container">
        <div className="demo-card">
          <p>未登录，请先登录。</p>
        </div>
      </div>
    )
  }

  const handleUserUpdated = (updated: AccountUser) => {
    setInfoMessage('资料已成功更新')
    void refreshUser()
    setTimeout(() => setInfoMessage(''), 3000)
  }

  const handleLogoutDone = () => {
    tokenStore.clear()
    navigate('/login')
  }

  const renderQr = async (otpauthUri: string): Promise<string> => {
    return QRCode.toDataURL(otpauthUri, { width: 200, margin: 1 })
  }

  return (
    <div className="demo-page-container">
      {/* User Header Profile Card */}
      <div className="demo-card demo-account-header">
        <div className="demo-account-header-left">
          <AvatarUploader
            client={accountClient}
            token={token}
            user={user}
            size={72}
            language="zh"
            onUploaded={handleUserUpdated}
            onDeleted={handleUserUpdated}
          />
          <div className="demo-account-header-info">
            <div className="demo-account-name-row">
              <h2>{user.username}</h2>
              {user.is_admin && <span className="demo-admin-tag">管理员</span>}
              {user.tier_name && (
                <TierBadge
                  name={user.tier_name}
                  color={user.tier_badge_color}
                />
              )}
            </div>
            <p className="demo-account-email">
              邮箱: {user.email} • 角色: {user.role || '默认'} • 审批:{' '}
              {user.approval_status === 'approved'
                ? '已通过'
                : user.approval_status === 'pending'
                  ? '审核中'
                  : '已拒绝'}
            </p>
          </div>
        </div>

        <div className="demo-account-header-right">
          <LogoutButton
            client={accountClient}
            token={token}
            refreshToken={tokenStore.getRefreshToken()}
            className="ak-btn ak-btn-outline"
            onDone={handleLogoutDone}
          >
            退出登录
          </LogoutButton>
        </div>
      </div>

      {infoMessage && <div className="ak-success" style={{ marginBottom: 16 }}>{infoMessage}</div>}

      {/* Tabs Layout */}
      <div className="demo-tabs-container">
        <div className="demo-tabs-nav">
          <button
            type="button"
            className={`demo-tab-btn ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}
          >
            👤 基本资料与密码
          </button>
          <button
            type="button"
            className={`demo-tab-btn ${activeTab === 'email' ? 'active' : ''}`}
            onClick={() => setActiveTab('email')}
          >
            ✉️ 修改邮箱
          </button>
          <button
            type="button"
            className={`demo-tab-btn ${activeTab === '2fa' ? 'active' : ''}`}
            onClick={() => setActiveTab('2fa')}
          >
            🔐 两步验证 (2FA)
          </button>
          <button
            type="button"
            className={`demo-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => setActiveTab('security')}
          >
            ⚙️ 会话与账号注销
          </button>
        </div>

        <div className="demo-card demo-tab-content">
          {activeTab === 'profile' && (
            <div>
              <h3 className="demo-tab-heading">个人资料与修改密码</h3>
              <p className="demo-muted" style={{ marginBottom: 16 }}>
                更新姓名、机构、性别及出生年月，也可同时修改登录密码。
              </p>
              <ProfileFields
                client={accountClient}
                token={token}
                user={user}
                language="zh"
                passwordEmailCode="auto"
                onSaved={(res) => handleUserUpdated(res.user)}
                onPasswordChanged={() => {
                  setInfoMessage('密码已成功修改！')
                  setTimeout(() => setInfoMessage(''), 3000)
                }}
              />
            </div>
          )}

          {activeTab === 'email' && (
            <div>
              <h3 className="demo-tab-heading">修改绑定邮箱</h3>
              <p className="demo-muted" style={{ marginBottom: 16 }}>
                向新邮箱发送验证码，验证后完成绑定。可在站内信箱查看验证码。
              </p>
              <ChangeEmailForm
                client={accountClient}
                token={token}
                user={user}
                requirePassword={true}
                language="zh"
                onChanged={handleUserUpdated}
              />
            </div>
          )}

          {activeTab === '2fa' && (
            <div>
              <h3 className="demo-tab-heading">两步验证 (2FA) 设置</h3>
              <p className="demo-muted" style={{ marginBottom: 16 }}>
                使用 Authenticator App 扫描二维码绑定 TOTP，或管理受信设备。
              </p>
              <TwoFactorSettings
                client={accountClient}
                token={token}
                username={user.username}
                language="zh"
                renderQr={renderQr}
                onUpdated={(status) => setTwoFactorStatus(status)}
              />
            </div>
          )}

          {activeTab === 'security' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div>
                <h3 className="demo-tab-heading">登出控制</h3>
                <p className="demo-muted" style={{ marginBottom: 12 }}>
                  登出当前设备或吊销所有设备的登录会话与刷新令牌。
                </p>
                <div style={{ display: 'flex', gap: 12 }}>
                  <LogoutButton
                    client={accountClient}
                    token={token}
                    refreshToken={tokenStore.getRefreshToken()}
                    onDone={handleLogoutDone}
                  >
                    登出当前设备
                  </LogoutButton>
                  <LogoutButton
                    client={accountClient}
                    token={token}
                    refreshToken={tokenStore.getRefreshToken()}
                    allDevices={true}
                    className="ak-btn ak-btn-danger"
                    onDone={handleLogoutDone}
                  >
                    登出全部设备
                  </LogoutButton>
                </div>
              </div>

              <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 24 }}>
                <h3 className="demo-tab-heading" style={{ color: '#d92d20' }}>
                  危险区域：注销账号
                </h3>
                {user.is_admin ? (
                  <div className="ak-warn">
                    🛡️ 当前账号是系统超级管理员，管理员账号禁止自助注销。
                  </div>
                ) : (
                  <div>
                    <p className="demo-muted" style={{ marginBottom: 12 }}>
                      注销后您的账号将无法恢复，相关凭据将全部被吊销。
                    </p>
                    <DeleteAccountForm
                      client={accountClient}
                      token={token}
                      twoFactorEnabled={twoFactorStatus?.enabled ?? false}
                      emailCodeAvailable={twoFactorStatus?.email_available ?? false}
                      language="zh"
                      onDeleted={handleLogoutDone}
                    />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
