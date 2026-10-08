import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { DemoI18nProvider } from './lib/i18n'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <DemoI18nProvider>
      <App />
    </DemoI18nProvider>
  </React.StrictMode>
)
