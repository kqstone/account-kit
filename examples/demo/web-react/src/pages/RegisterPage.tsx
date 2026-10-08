import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { RegisterForm, type AccountUser } from '@kqstone/account-ui-react'
import { accountClient } from '../lib/auth'
import { useAuth } from '../context/AuthContext'
import { useDemoI18n } from '../lib/i18n'

export const RegisterPage: React.FC = () => {
  const { toggleOutboxDrawer } = useAuth()
  const { t } = useDemoI18n()
  const [registeredUser, setRegisteredUser] = useState<AccountUser | null>(null)

  return (
    <div className="demo-page-container">
      <div className="demo-card demo-auth-card">
        <h2 className="demo-auth-title">{t.registerTitle}</h2>
        <p className="demo-muted demo-auth-subtitle">
          {t.registerDesc}
        </p>

        <div className="demo-tip-card">
          <span>{t.registerHintBefore}</span>
          <button
            type="button"
            className="ak-link"
            onClick={toggleOutboxDrawer}
            style={{ fontWeight: 600, margin: '0 4px' }}
          >
            📬 {t.outbox}
          </button>
          <span>{t.registerHintAfter}</span>
        </div>

        {registeredUser ? (
          <div className="demo-success-box">
            <div className="ak-success" style={{ marginBottom: 16 }}>
              {registeredUser.approval_status === 'pending'
                ? t.registerSuccessPending.replace('{username}', registeredUser.username)
                : t.registerSuccessDirect.replace('{username}', registeredUser.username)}
            </div>
            <Link to="/login" className="ak-btn ak-btn-primary" style={{ display: 'inline-block' }}>
              {t.goLoginBtn}
            </Link>
          </div>
        ) : (
          <RegisterForm
            client={accountClient}
            onSuccess={(user) => setRegisteredUser(user)}
          />
        )}

        <div className="demo-auth-footer">
          <span>{t.haveAccount}</span>
          <Link to="/login" className="ak-link" style={{ marginLeft: 6 }}>
            {t.goLoginNow}
          </Link>
        </div>
      </div>
    </div>
  )
}
