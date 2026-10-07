import React from 'react'
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { Navbar } from './components/Navbar'
import { OutboxDrawer } from './components/OutboxDrawer'
import {
  SetupGuard,
  RequireAuth,
  RequireAdmin,
} from './components/Guards'
import { SetupPage } from './pages/SetupPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { AccountPage } from './pages/AccountPage'
import { AdminUsersPage } from './pages/AdminUsersPage'
import { AdminAuditPage } from './pages/AdminAuditPage'
import { OutboxPage } from './pages/OutboxPage'
import { NotFoundPage } from './pages/NotFoundPage'

const HomeRedirect: React.FC = () => {
  const { initialized, token } = useAuth()
  if (initialized === false) {
    return <Navigate to="/setup" replace />
  }
  if (token) {
    return <Navigate to="/account" replace />
  }
  return <Navigate to="/login" replace />
}

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <SetupGuard>
          <div className="demo-layout">
            <Navbar />
            <main className="demo-main">
              <Routes>
                {/* Index Route */}
                <Route path="/" element={<HomeRedirect />} />

                {/* Setup */}
                <Route path="/setup" element={<SetupPage />} />

                {/* Auth */}
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/reset" element={<ResetPasswordPage />} />

                {/* Account */}
                <Route
                  path="/account"
                  element={
                    <RequireAuth>
                      <AccountPage />
                    </RequireAuth>
                  }
                />

                {/* Admin */}
                <Route
                  path="/admin"
                  element={
                    <RequireAdmin>
                      <AdminUsersPage />
                    </RequireAdmin>
                  }
                />
                <Route
                  path="/admin/audit"
                  element={
                    <RequireAdmin>
                      <AdminAuditPage />
                    </RequireAdmin>
                  }
                />

                {/* Outbox */}
                <Route path="/outbox" element={<OutboxPage />} />

                {/* 404 */}
                <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </main>
            <OutboxDrawer />
          </div>
        </SetupGuard>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
