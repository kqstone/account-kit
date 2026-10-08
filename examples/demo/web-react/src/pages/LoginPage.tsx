import React, { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  LoginForm,
  TwoFactorLoginDialog,
  getTrustedDeviceToken,
  trustedDeviceScope,
  type LoginSecondFactorResult,
  type MfaChallenge,
  type TokenPair,
} from '@kqstone/account-ui-react'
import { accountClient, tokenStore } from '../lib/auth'
import { useAuth } from '../context/AuthContext'
import { useDemoI18n } from '../lib/i18n'

export const LoginPage: React.FC = () => {
  const { refreshUser } = useAuth()
  const { t } = useDemoI18n()
  const navigate = useNavigate()
  const location = useLocation()
  const stateMessage = (location.state as { message?: string })?.message

  const [mfaChallenge, setMfaChallenge] = useState<
    (MfaChallenge & { username: string; password: string; force: boolean }) | null
  >(null)
  const [error, setError] = useState<string>('')

  const handleLoginSuccess = async () => {
    await refreshUser()
    const target = (location.state as { from?: { pathname?: string } })?.from?.pathname || '/account'
    navigate(target, { replace: true })
  }

  const handleTokens = (tokens: TokenPair) => {
    tokenStore.set(tokens)
  }

  const handleMfaSuccess = async (data: LoginSecondFactorResult) => {
    tokenStore.set(data)
    setMfaChallenge(null)
    await handleLoginSuccess()
  }

  return (
    <div className="demo-page-container">
      <div className="demo-card demo-auth-card">
        <h2 className="demo-auth-title">{t.loginTitle}</h2>
        <p className="demo-muted demo-auth-subtitle">
          {t.loginDesc}
        </p>

        {stateMessage && (
          <div className="ak-success" style={{ marginBottom: 16 }}>
            {stateMessage}
          </div>
        )}

        {error && (
          <div className="ak-error" style={{ marginBottom: 16 }}>
            {error}
          </div>
        )}

        <LoginForm
          client={accountClient}
          trustedDeviceToken={(username: string) =>
            getTrustedDeviceToken(trustedDeviceScope('', username))
          }
          onTokens={handleTokens}
          onSuccess={handleLoginSuccess}
          onMfa={(challenge) => {
            setError('')
            setMfaChallenge(challenge)
          }}
        />

        {mfaChallenge && (
          <TwoFactorLoginDialog
            client={accountClient}
            challenge={mfaChallenge}
            force={mfaChallenge.force}
            scope={trustedDeviceScope('', mfaChallenge.username)}
            onSuccess={handleMfaSuccess}
            onCancel={() => setMfaChallenge(null)}
            onExpired={(msg) => {
              setMfaChallenge(null)
              setError(msg || t.mfaExpired)
            }}
          />
        )}

        <div className="demo-auth-footer">
          <Link to="/reset" className="ak-link">
            {t.forgot}
          </Link>
          <span className="demo-divider">•</span>
          <Link to="/register" className="ak-link">
            {t.noAccount}
          </Link>
        </div>
      </div>
    </div>
  )
}
