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
  <TwoFactorSettings v-if="token" :client="client" :token="token" language="zh" />
</template>
```

文案通过 `language`（`zh` / `en`）和 `labels` 覆盖，不依赖 vue-i18n。二维码：安装 peer `qrcode`，或传入 `renderQr(otpauthUri) => dataUrl`。

样式在组件首次渲染时以 `<style id="account-kit-ui">` 注入，class 前缀为 `ak-`。需要 `vue` ^3.2。

## 导出

`LoginForm` `RegisterForm` `ResetPasswordForm` `TwoFactorSettings` `TwoFactorLoginDialog` `AvatarUploader` `UserAvatar` `ProfileFields` `TierBadge` `createAccountClient` `getMfaChallenge` `getTrustedDeviceToken` `saveTrustedDeviceToken` `clearTrustedDeviceToken` `clearTrustedDeviceTokensForUser` `trustedDeviceScope`

MIT License
