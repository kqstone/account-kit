import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { RegisterForm, type AccountUser } from '@kqstone/account-ui-react'
import { accountClient } from '../lib/auth'
import { useAuth } from '../context/AuthContext'

export const RegisterPage: React.FC = () => {
  const { toggleOutboxDrawer } = useAuth()
  const [registeredUser, setRegisteredUser] = useState<AccountUser | null>(null)

  return (
    <div className="demo-page-container">
      <div className="demo-card demo-auth-card">
        <h2 className="demo-auth-title">注册新账号</h2>
        <p className="demo-muted demo-auth-subtitle">
          请填写账号基本信息并输入邮箱验证码
        </p>

        <div className="demo-tip-card">
          <span>💡 注册验证码已发送至控制台，可在</span>
          <button
            type="button"
            className="ak-link"
            onClick={toggleOutboxDrawer}
            style={{ fontWeight: 600, margin: '0 4px' }}
          >
            📬 站内信箱
          </button>
          <span>中实时查看并一键复制。</span>
        </div>

        {registeredUser ? (
          <div className="demo-success-box">
            <div className="ak-success" style={{ marginBottom: 16 }}>
              {registeredUser.approval_status === 'pending'
                ? `🎉 注册成功！用户「${registeredUser.username}」处于待审批状态，管理员审批通过后方可登录。`
                : `🎉 注册成功！用户「${registeredUser.username}」已创建，请前往登录。`}
            </div>
            <Link to="/login" className="ak-btn ak-btn-primary" style={{ display: 'inline-block' }}>
              前往登录
            </Link>
          </div>
        ) : (
          <RegisterForm
            client={accountClient}
            language="zh"
            onSuccess={(user) => setRegisteredUser(user)}
          />
        )}

        <div className="demo-auth-footer">
          <span>已有账号？</span>
          <Link to="/login" className="ak-link" style={{ marginLeft: 6 }}>
            立即登录
          </Link>
        </div>
      </div>
    </div>
  )
}
