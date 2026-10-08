# @kqstone/account-ui-react

[account-kit](https://pypi.org/project/account-kit/) 的 React 界面组件。不依赖 antd。

- 表单：`LoginForm`、`RegisterForm`、`ResetPasswordForm`
- 两步验证：`TwoFactorSettings`、`TwoFactorLoginDialog`
- 资料：`ProfileFields`、`AvatarUploader`、`UserAvatar`
- 其它：`TierBadge`、`createAccountClient`

安装前在项目根配置 GitHub Packages（见仓库 README 的 `.npmrc` 说明）：

```bash
npm install @kqstone/account-ui-react
# 可选：用于设置页二维码。也可传入 renderQr。
npm install qrcode
```

```tsx
import { createAccountClient, LoginForm, TwoFactorLoginDialog, TwoFactorSettings } from "@kqstone/account-ui-react"

const client = createAccountClient("/api/auth")

export function Login() {
  return <LoginForm client={client} deviceName="web" onSuccess={(token) => localStorage.setItem("token", token)} onMfa={(challenge) => console.log(challenge)} />
}
```

文案通过 `language`（`zh-CN` / `en`，旧值 `zh` 仍兼容）和 `labels` 覆盖。也可用 `AccountKitProvider`；对接 i18next 时用 duck-typed `followI18next(i18n)`（订阅 `languageChanged`，不 import i18next）。`createAccountClient({ getLocale })` 每请求带 `X-Locale`。二维码：安装 peer `qrcode`，或传入 `renderQr(otpauthUri) => dataUrl`。

样式在组件首次渲染时以 `<style id="account-kit-ui">` 注入，class 前缀为 `ak-`。需要 `react` 18 或 19。

## 导出

`LoginForm` `RegisterForm` `ResetPasswordForm` `TwoFactorSettings` `TwoFactorLoginDialog` `AvatarUploader` `UserAvatar` `ProfileFields` `TierBadge` `createAccountClient` `AccountKitProvider` `useAccountI18n` `followI18next` `formatError` `resolveLocale` `getMfaChallenge` `getTrustedDeviceToken` `saveTrustedDeviceToken` `clearTrustedDeviceToken` `clearTrustedDeviceTokensForUser` `trustedDeviceScope`

MIT License
