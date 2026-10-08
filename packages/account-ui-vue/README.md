# @kqstone/account-ui-vue

[account-kit](https://pypi.org/project/account-kit/) 的 Vue 3 界面组件。

- 表单：`LoginForm`、`RegisterForm`、`ResetPasswordForm`
- 两步验证：`TwoFactorSettings`、`TwoFactorLoginDialog`
- 资料：`ProfileFields`、`AvatarUploader`、`UserAvatar`
- 其它：`TierBadge`、`createAccountClient`

安装前在项目根配置 GitHub Packages（见仓库 README 的 `.npmrc` 说明）：

```bash
npm install @kqstone/account-ui-vue
# 可选：用于设置页二维码。也可传入 renderQr。
npm install qrcode
```

```vue
<script setup lang="ts">
import { ref } from "vue"
import {
  createAccountClient,
  LoginForm,
  TwoFactorLoginDialog,
  TwoFactorSettings,
  getMfaChallenge,
  getTrustedDeviceToken,
  trustedDeviceScope,
} from "@kqstone/account-ui-vue"

const client = createAccountClient("/api/auth")
const token = ref("")
const mfa = ref(null)

function onSuccess(accessToken) {
  token.value = accessToken
  localStorage.setItem("token", accessToken)
}
</script>

<template>
  <LoginForm
    :client="client"
    device-name="web"
    :trusted-device-token="(name) => getTrustedDeviceToken(trustedDeviceScope('', name))"
    @success="onSuccess"
    @mfa="mfa = $event"
  />
  <TwoFactorLoginDialog
    v-if="mfa"
    :client="client"
    :challenge="mfa"
    device-name="web"
    :scope="trustedDeviceScope('', mfa.username)"
    @success="(data) => { onSuccess(data.access_token); mfa = null }"
    @cancel="mfa = null"
    @expired="mfa = null"
  />
  <TwoFactorSettings v-if="token" :client="client" :token="token" />
</template>
```

文案通过 `language`（`zh-CN` / `en`，旧值 `zh` 仍兼容）和组件 `labels` 覆盖。也可用插件 `accountKitI18n({ locale, i18n, messages })` 或 `provideAccountI18n(followVueI18n(i18n), messages)`；对接 vue-i18n 时把实例传给插件的 `i18n`，或用 duck-typed `followVueI18n(i18n)`（不 import vue-i18n）。`createAccountClient({ getLocale: followVueI18n(i18n) })` 每请求带 `X-Locale`。二维码：安装 peer `qrcode`，或传入 `renderQr(otpauthUri) => dataUrl`。

样式在组件首次渲染时以 `<style id="account-kit-ui">` 注入，class 前缀为 `ak-`。需要 `vue` ^3.2。

## 导出

`LoginForm` `RegisterForm` `ResetPasswordForm` `TwoFactorSettings` `TwoFactorLoginDialog` `AvatarUploader` `UserAvatar` `ProfileFields` `TierBadge` `createAccountClient` `accountKitI18n` `provideAccountI18n` `useAccountI18n` `followVueI18n` `formatError` `resolveLocale` `getMfaChallenge` `getTrustedDeviceToken` `saveTrustedDeviceToken` `clearTrustedDeviceToken` `clearTrustedDeviceTokensForUser` `trustedDeviceScope`

MIT License
