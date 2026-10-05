# @kqstone/account-ui-react

[account-kit](https://pypi.org/project/account-kit/) 的 React 界面组件：`LoginForm`、`RegisterForm`、`ResetPasswordForm`、`TierBadge`，以及请求客户端 `createAccountClient`。

安装前在项目根配置 GitHub Packages（见仓库 README 的 `.npmrc` 说明）：

```bash
npm install @kqstone/account-ui-react
```

```tsx
import { createAccountClient, LoginForm } from "@kqstone/account-ui-react"

const client = createAccountClient("/api/auth")

export function Login() {
  return <LoginForm client={client} deviceName="web" onSuccess={(token) => localStorage.setItem("token", token)} />
}
```

样式在组件首次渲染时以 `<style id="account-kit-ui">` 注入，不需要单独引入 CSS。需要 `react` 18 或 19。

MIT License
