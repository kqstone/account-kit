import React from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { UserAvatar, TierBadge } from '@kqstone/account-ui-react'
import { accountClient } from '../lib/auth'

export const Navbar: React.FC = () => {
  const { initialized, user, token, logout, toggleOutboxDrawer } = useAuth()
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
                      登录
                    </NavLink>
                    <NavLink
                      to="/register"
                      className={({ isActive }) =>
                        isActive ? 'demo-nav-link active' : 'demo-nav-link'
                      }
                    >
                      注册
                    </NavLink>
                  </>
                ) : (
                  <NavLink
                    to="/account"
                    className={({ isActive }) =>
                      isActive ? 'demo-nav-link active' : 'demo-nav-link'
                    }
                  >
                    账号设置
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
                      用户管理
                    </NavLink>
                    <NavLink
                      to="/admin/audit"
                      className={({ isActive }) =>
                        isActive ? 'demo-nav-link active' : 'demo-nav-link'
                      }
                    >
                      审计日志
                    </NavLink>
                  </>
                )}

                <NavLink
                  to="/outbox"
                  className={({ isActive }) =>
                    isActive ? 'demo-nav-link active' : 'demo-nav-link'
                  }
                >
                  站内信箱
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
                  初始化向导
                </NavLink>
                <NavLink
                  to="/outbox"
                  className={({ isActive }) =>
                    isActive ? 'demo-nav-link active' : 'demo-nav-link'
                  }
                >
                  站内信箱
                </NavLink>
              </>
            )}
          </nav>
        </div>

        <div className="demo-nav-right">
          <button
            type="button"
            className="demo-btn-outbox-toggle"
            onClick={toggleOutboxDrawer}
            title="打开/关闭右侧站内信箱"
          >
            📬 <span>侧栏信箱</span>
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
                <span className="demo-admin-tag">管理员</span>
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
                退出
              </button>
            </div>
          ) : !initialized ? (
            <span className="demo-status-tag warning">未初始化</span>
          ) : (
            <Link to="/login" className="demo-btn-login-sm">
              去登录
            </Link>
          )}
        </div>
      </div>
    </header>
  )
}
