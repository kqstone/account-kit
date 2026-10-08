import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useDemoI18n } from '../lib/i18n'

export const SetupGuard: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { initialized } = useAuth()
  const { t } = useDemoI18n()
  const location = useLocation()

  if (initialized === null) {
    return (
      <div className="demo-loading-screen">
        <div className="demo-spinner" />
        <p>{t.checkInitStatus}</p>
      </div>
    )
  }

  // If not initialized, force to /setup
  if (!initialized && location.pathname !== '/setup') {
    return <Navigate to="/setup" replace />
  }

  // If already initialized and on /setup, redirect to /login
  if (initialized && location.pathname === '/setup') {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export const RequireAuth: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { token, loadingUser } = useAuth()
  const { t } = useDemoI18n()
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (loadingUser) {
    return (
      <div className="demo-loading-screen">
        <div className="demo-spinner" />
        <p>{t.loadingUserInfo}</p>
      </div>
    )
  }

  return <>{children}</>
}

export const RequireAdmin: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { token, user, loadingUser } = useAuth()
  const { t } = useDemoI18n()
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (loadingUser) {
    return (
      <div className="demo-loading-screen">
        <div className="demo-spinner" />
        <p>{t.checkingAdminPerm}</p>
      </div>
    )
  }

  if (!user?.is_admin) {
    return (
      <div className="demo-container">
        <div className="demo-card demo-card-danger">
          <h2>{t.forbidden403Title}</h2>
          <p>{t.forbidden403Desc}</p>
          <div style={{ marginTop: 16 }}>
            <a href="/account" className="ak-btn">
              {t.backToAccount}
            </a>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
