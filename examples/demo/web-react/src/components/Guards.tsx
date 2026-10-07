import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export const SetupGuard: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { initialized } = useAuth()
  const location = useLocation()

  if (initialized === null) {
    return (
      <div className="demo-loading-screen">
        <div className="demo-spinner" />
        <p>检查系统初始化状态…</p>
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
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (loadingUser) {
    return (
      <div className="demo-loading-screen">
        <div className="demo-spinner" />
        <p>加载用户信息…</p>
      </div>
    )
  }

  return <>{children}</>
}

export const RequireAdmin: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { token, user, loadingUser } = useAuth()
  const location = useLocation()

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (loadingUser) {
    return (
      <div className="demo-loading-screen">
        <div className="demo-spinner" />
        <p>校验管理员权限…</p>
      </div>
    )
  }

  if (!user?.is_admin) {
    return (
      <div className="demo-container">
        <div className="demo-card demo-card-danger">
          <h2>403 权限不足</h2>
          <p>当前页面需要管理员权限 (`is_admin: true`)。</p>
          <div style={{ marginTop: 16 }}>
            <a href="/account" className="ak-btn">
              返回个人中心
            </a>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
