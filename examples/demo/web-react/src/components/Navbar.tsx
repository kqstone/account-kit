import React from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { UserAvatar, TierBadge } from '@kqstone/account-ui-react'
import { accountClient } from '../lib/auth'
import { useDemoI18n } from '../lib/i18n'

export const Navbar: React.FC = () => {
  const { initialized, user, token, logout, toggleOutboxDrawer } = useAuth()
  const { locale, setLocale, t } = useDemoI18n()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <header className="demo-header">
      <div className="demo-header-inner">
        <div className="demo-nav-left">
          <Link to="/" className="demo-logo">
            <span className="demo-logo-icon">🛡️</span>
            <span className="demo-logo-text">Account Kit Demo</span>
          </Link>

          <nav className="demo-nav-links">
            {initialized ? (
              <>
                {!token ? (
                  <>
                    <NavLink
                      to="/login"
                      className={({ isActive }) =>
                        isActive ? 'demo-nav-link active' : 'demo-nav-link'
                      }
                    >
                      {t.login}
                    </NavLink>
                    <NavLink
                      to="/register"
                      className={({ isActive }) =>
                        isActive ? 'demo-nav-link active' : 'demo-nav-link'
                      }
                    >
                      {t.register}
                    </NavLink>
                  </>
                ) : (
                  <NavLink
                    to="/account"
                    className={({ isActive }) =>
                      isActive ? 'demo-nav-link active' : 'demo-nav-link'
                    }
                  >
                    {t.account}
                  </NavLink>
                )}

                {user?.is_admin && (
                  <>
                    <NavLink
                      to="/admin"
                      end
                      className={({ isActive }) =>
                        isActive ? 'demo-nav-link active' : 'demo-nav-link'
                      }
                    >
                      {t.adminUsers}
                    </NavLink>
                    <NavLink
                      to="/admin/audit"
                      className={({ isActive }) =>
                        isActive ? 'demo-nav-link active' : 'demo-nav-link'
                      }
                    >
                      {t.adminAudit}
                    </NavLink>
                  </>
                )}

                <NavLink
                  to="/outbox"
                  className={({ isActive }) =>
                    isActive ? 'demo-nav-link active' : 'demo-nav-link'
                  }
                >
                  {t.outbox}
                </NavLink>
              </>
            ) : (
              <>
                <NavLink
                  to="/setup"
                  className={({ isActive }) =>
                    isActive ? 'demo-nav-link active' : 'demo-nav-link'
                  }
                >
                  {t.setup}
                </NavLink>
                <NavLink
                  to="/outbox"
                  className={({ isActive }) =>
                    isActive ? 'demo-nav-link active' : 'demo-nav-link'
                  }
                >
                  {t.outbox}
                </NavLink>
              </>
            )}
          </nav>
        </div>

        <div className="demo-nav-right">
          <div className="lang-switch" role="group" aria-label={`${t.langZh} / ${t.langEn}`}>
            <button
              type="button"
              className={locale === 'zh-CN' ? 'active' : ''}
              onClick={() => setLocale('zh-CN')}
            >
              {t.langZh}
            </button>
            <button
              type="button"
              className={locale === 'en' ? 'active' : ''}
              onClick={() => setLocale('en')}
            >
              {t.langEn}
            </button>
          </div>
          <button
            type="button"
            className="demo-btn-outbox-toggle"
            onClick={toggleOutboxDrawer}
            title={t.drawerTitle}
          >
            📬 <span>{t.drawerMailbox}</span>
          </button>

          {user && token ? (
            <div className="demo-user-badge">
              <UserAvatar
                user={user}
                client={accountClient}
                token={token}
                size={28}
              />
              <span className="demo-username">{user.username}</span>
              {user.is_admin && (
                <span className="demo-admin-tag">{t.admin}</span>
              )}
              {user.tier_name && (
                <TierBadge
                  name={user.tier_name}
                  color={user.tier_badge_color}
                />
              )}
              <button
                type="button"
                className="demo-btn-link demo-logout-link"
                onClick={handleLogout}
              >
                {t.logout}
              </button>
            </div>
          ) : !initialized ? (
            <span className="demo-status-tag warning">{t.notInit}</span>
          ) : (
            <Link to="/login" className="demo-btn-login-sm">
              {t.goLogin}
            </Link>
          )}
        </div>
      </div>
    </header>
  )
}
