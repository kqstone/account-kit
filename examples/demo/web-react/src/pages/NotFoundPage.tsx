import React from 'react'
import { Link } from 'react-router-dom'

export const NotFoundPage: React.FC = () => {
  return (
    <div className="demo-page-container">
      <div className="demo-card" style={{ textAlign: 'center', padding: '48px 24px' }}>
        <h2 style={{ fontSize: 48, margin: '0 0 16px', color: '#8c8c8c' }}>404</h2>
        <h3 style={{ margin: '0 0 12px' }}>页面不存在</h3>
        <p className="demo-muted" style={{ marginBottom: 24 }}>
          抱歉，您访问的页面不存在或已被移除。
        </p>
        <Link to="/" className="ak-btn ak-btn-primary">
          返回首页
        </Link>
      </div>
    </div>
  )
}
