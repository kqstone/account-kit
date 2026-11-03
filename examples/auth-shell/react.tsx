import { useState } from "react"
import { createRoot } from "react-dom/client"
import { AuthShell, CodeInputRow, LoginForm, RegisterForm, ResetPasswordForm } from "../../packages/account-ui-react/src/index"
import { mockClient } from "./mockClient"

const page = new URLSearchParams(location.search).get("page") || "login"
const native = new URLSearchParams(location.search).has("native")
const logo = <span style={{ color: "#fff", fontWeight: 700, fontSize: 22 }}>A</span>
const lang = <button style={{ background: "rgba(255,255,255,.2)", color: "#fff", border: 0, borderRadius: 6, padding: "4px 8px" }}>中 / EN</button>

function Admin() {
  const [code, setCode] = useState("")
  return (
    <form className="ak-form">
      <label>用户名<input /></label>
      <label>密码<input type="password" /></label>
      <CodeInputRow label="验证码" value={code} onChange={setCode} maxLength={6} inputMode="numeric" buttonText="发送验证码" />
      <button type="submit">登录</button>
    </form>
  )
}

function App() {
  const common = { brandName: "Account Kit", logo, copyright: "© 2026 Account Kit", languageSwitch: lang, native }
  if (page === "register")
    return <AuthShell {...common} title="注册" footer={<a href="#">已有账号？登录</a>}><RegisterForm client={mockClient} onSuccess={() => undefined} /></AuthShell>
  if (page === "reset")
    return <AuthShell {...common} title="找回密码" footer={<a href="#">返回登录</a>}><ResetPasswordForm client={mockClient} onSuccess={() => undefined} /></AuthShell>
  if (page === "admin")
    return <AuthShell {...common} variant="admin" brandName="系统管理" brandSubtitle="管理员控制台" title="管理员登录"><Admin /></AuthShell>
  return <AuthShell {...common} title="登录" footer={<span><a href="#">注册</a> · <a href="#">忘记密码</a></span>}><LoginForm client={mockClient} onSuccess={() => undefined} /></AuthShell>
}
createRoot(document.getElementById("app")!).render(<App />)
