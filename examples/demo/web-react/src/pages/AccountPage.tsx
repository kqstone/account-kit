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
import { useDemoI18n } from '../lib/i18n'

export const AccountPage: React.FC = () => {
  const { user, token, refreshUser, logout } = useAuth()
  const { t } = useDemoI18n()
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
          <p>{t.notLoggedIn}</p>
        </div>
      </div>
    )
  }

  const handleUserUpdated = (updated: AccountUser) => {
    setInfoMessage(t.profileUpdated)
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
            
            onUploaded={handleUserUpdated}
            onDeleted={handleUserUpdated}
          />
          <div className="demo-account-header-info">
            <div className="demo-account-name-row">
              <h2>{user.username}</h2>
              {user.is_admin && <span className="demo-admin-tag">{t.admin}</span>}
              {user.tier_name && (
                <TierBadge
                  name={user.tier_name}
                  color={user.tier_badge_color}
                />
              )}
            </div>
            <p className="demo-account-email">
              {t.emailLabel}: {user.email} • {t.roleLabel}: {user.role || t.roleDefault} • {t.approvalLabel}:{' '}
              {user.approval_status === 'approved'
                ? t.statusApproved
                : user.approval_status === 'pending'
                  ? t.statusReviewing
                  : t.statusRejected}
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
            {t.logout}
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
            {t.tabProfilePasswordWithIcon}
          </button>
          <button
            type="button"
            className={`demo-tab-btn ${activeTab === 'email' ? 'active' : ''}`}
            onClick={() => setActiveTab('email')}
          >
            {t.tabEmailWithIcon}
          </button>
          <button
            type="button"
            className={`demo-tab-btn ${activeTab === '2fa' ? 'active' : ''}`}
            onClick={() => setActiveTab('2fa')}
          >
            {t.tab2faWithIcon}
          </button>
          <button
            type="button"
            className={`demo-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => setActiveTab('security')}
          >
            {t.tabSessionsDangerWithIcon}
          </button>
        </div>

        <div className="demo-card demo-tab-content">
          {activeTab === 'profile' && (
            <div>
              <h3 className="demo-tab-heading">{t.accountProfileHeadingReact}</h3>
              <p className="demo-muted" style={{ marginBottom: 16 }}>
                {t.accountProfileDescReact}
              </p>
              <ProfileFields
                client={accountClient}
                token={token}
                user={user}
                
                passwordEmailCode="auto"
                onSaved={(res) => handleUserUpdated(res.user)}
                onPasswordChanged={() => {
                  setInfoMessage(t.passwordUpdated)
                  setTimeout(() => setInfoMessage(''), 3000)
                }}
              />
            </div>
          )}

          {activeTab === 'email' && (
            <div>
              <h3 className="demo-tab-heading">{t.accountEmailHeading}</h3>
              <p className="demo-muted" style={{ marginBottom: 16 }}>
                {t.accountEmailDescReact}
              </p>
              <ChangeEmailForm
                client={accountClient}
                token={token}
                user={user}
                requirePassword={true}
                
                onChanged={handleUserUpdated}
              />
            </div>
          )}

          {activeTab === '2fa' && (
            <div>
              <h3 className="demo-tab-heading">{t.account2faHeading}</h3>
              <p className="demo-muted" style={{ marginBottom: 16 }}>
                {t.account2faDescReact}
              </p>
              <TwoFactorSettings
                client={accountClient}
                token={token}
                username={user.username}
                
                renderQr={renderQr}
                onUpdated={(status) => setTwoFactorStatus(status)}
              />
            </div>
          )}

          {activeTab === 'security' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div>
                <h3 className="demo-tab-heading">{t.accountLogoutHeading}</h3>
                <p className="demo-muted" style={{ marginBottom: 12 }}>
                  {t.accountLogoutDesc}
                </p>
                <div style={{ display: 'flex', gap: 12 }}>
                  <LogoutButton
                    client={accountClient}
                    token={token}
                    refreshToken={tokenStore.getRefreshToken()}
                    onDone={handleLogoutDone}
                  >
                    {t.logoutCurrentDevice}
                  </LogoutButton>
                  <LogoutButton
                    client={accountClient}
                    token={token}
                    refreshToken={tokenStore.getRefreshToken()}
                    allDevices={true}
                    className="ak-btn ak-btn-danger"
                    onDone={handleLogoutDone}
                  >
                    {t.logoutAllDevices}
                  </LogoutButton>
                </div>
              </div>

              <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 24 }}>
                <h3 className="demo-tab-heading" style={{ color: '#d92d20' }}>
                  {t.dangerZoneHeading}
                </h3>
                {user.is_admin ? (
                  <div className="ak-warn">
                    {t.deleteAccountAdminBlockedReact}
                  </div>
                ) : (
                  <div>
                    <p className="demo-muted" style={{ marginBottom: 12 }}>
                      {t.deleteAccountWarningReact}
                    </p>
                    <DeleteAccountForm
                      client={accountClient}
                      token={token}
                      twoFactorEnabled={twoFactorStatus?.enabled ?? false}
                      emailCodeAvailable={twoFactorStatus?.email_available ?? false}
                      
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
