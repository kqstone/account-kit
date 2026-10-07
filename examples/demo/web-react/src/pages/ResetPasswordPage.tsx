import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { ResetPasswordForm } from '@kqstone/account-ui-react'
import { accountClient } from '../lib/auth'
import { useAuth } from '../context/AuthContext'

export const ResetPasswordPage: React.FC = () => {
  const { toggleOutboxDrawer } = useAuth()
  const [success, setSuccess] = useState(false)

  return (
    <div className="demo-page-container">
      <div className="demo-card demo-auth-card">
        <h2 className="demo-auth-title">找回密码</h2>
        <p className="demo-muted demo-auth-subtitle">
          输入注册邮箱获取验证码，并设置新密码
        </p>

        <div className="demo-tip-card">
          <span>💡 重置密码验证码可在</span>
          <button
            type="button"
            className="ak-link"
            onClick={toggleOutboxDrawer}
            style={{ fontWeight: 600, margin: '0 4px' }}
          >
            📬 站内信箱
          </button>
          <span>中查看。</span>
        </div>

        {success ? (
          <div className="demo-success-box">
            <div className="ak-success" style={{ marginBottom: 16 }}>
              🎉 密码重置成功！请使用新密码重新登录。
            </div>
            <Link to="/login" className="ak-btn ak-btn-primary" style={{ display: 'inline-block' }}>
              前往登录
            </Link>
          </div>
        ) : (
          <ResetPasswordForm
            client={accountClient}
            language="zh"
            onSuccess={() => setSuccess(true)}
          />
        )}

        <div className="demo-auth-footer">
          <Link to="/login" className="ak-link">
            返回登录
          </Link>
          <span className="demo-divider">•</span>
          <Link to="/register" className="ak-link">
            注册账号
          </Link>
        </div>
      </div>
    </div>
  )
}
