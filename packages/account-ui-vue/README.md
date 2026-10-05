# @kqstone/account-ui-vue

[account-kit](https://pypi.org/project/account-kit/) 的 Vue 3 界面组件：`LoginForm`、`RegisterForm`、`ResetPasswordForm`、`TierBadge`，以及请求客户端 `createAccountClient`。

安装前在项目根配置 GitHub Packages（见仓库 README 的 `.npmrc` 说明）：

```bash
npm install @kqstone/account-ui-vue
```

```vue
<script setup lang="ts">
import { createAccountClient, LoginForm } from "@kqstone/account-ui-vue"

const client = createAccountClient("/api/auth")
function onSuccess(token: string) {
  localStorage.setItem("token", token)
}
</script>

<template>
  <LoginForm :client="client" device-name="web" @success="onSuccess" />
</template>
```

样式在组件首次渲染时以 `<style id="account-kit-ui">` 注入，不需要单独引入 CSS。需要 `vue` ^3.2。

MIT License
