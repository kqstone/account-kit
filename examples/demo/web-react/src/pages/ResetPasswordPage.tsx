import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { ResetPasswordForm } from '@kqstone/account-ui-react'
import { accountClient } from '../lib/auth'
import { useAuth } from '../context/AuthContext'
import { useDemoI18n } from '../lib/i18n'

export const ResetPasswordPage: React.FC = () => {
  const { toggleOutboxDrawer } = useAuth()
  const { t } = useDemoI18n()
  const [success, setSuccess] = useState(false)

  return (
    <div className="demo-page-container">
      <div className="demo-card demo-auth-card">
        <h2 className="demo-auth-title">{t.resetTitle}</h2>
        <p className="demo-muted demo-auth-subtitle">
          {t.resetDesc}
        </p>

        <div className="demo-tip-card">
          <span>{t.resetHintBefore}</span>
          <button
            type="button"
            className="ak-link"
            onClick={toggleOutboxDrawer}
            style={{ fontWeight: 600, margin: '0 4px' }}
          >
            📬 {t.outbox}
          </button>
          <span>{t.resetHintAfter}</span>
        </div>

        {success ? (
          <div className="demo-success-box">
            <div className="ak-success" style={{ marginBottom: 16 }}>
              {t.resetOk}
            </div>
            <Link to="/login" className="ak-btn ak-btn-primary" style={{ display: 'inline-block' }}>
              {t.goLoginBtn}
            </Link>
          </div>
        ) : (
          <ResetPasswordForm
            client={accountClient}
            onSuccess={() => setSuccess(true)}
          />
        )}

        <div className="demo-auth-footer">
          <Link to="/login" className="ak-link">
            {t.backLogin}
          </Link>
          <span className="demo-divider">•</span>
          <Link to="/register" className="ak-link">
            {t.registerAccount}
          </Link>
        </div>
      </div>
    </div>
  )
}
