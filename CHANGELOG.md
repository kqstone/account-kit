# Changelog

## 0.6.0

新增登录外壳 `AuthShell` 与验证码行 `CodeInputRow`（React / Vue，DOM 与 class 一致），默认文案精简。后端无改动、无迁移。

- `AuthShell`：品牌头（logo / 名称 / 副标题，可点击，`headerAttrs` 透传，如 Tauri `data-tauri-drag-region`）、语言切换、标题卡片、页脚、版权。100dvh 布局，头部 / 卡片头 / 卡片脚固定，仅 `.ak-shell-body` 滚动。`native`（默认 `detectNative()`，识别 Capacitor）隐藏语言切换与版权。`variant="admin"` 走 `--ak-shell-admin-bg`。
- CSS 变量（中性默认值，可在 `:root` / `.ak-shell` / `style` 覆盖）：`--ak-shell-bg`、`--ak-shell-primary`、`--ak-shell-card-bg`、`--ak-shell-card-radius`、`--ak-control-height`（默认 40px）。样式只作用于 `.ak-shell-*` / `.ak-code-*`，不写全局 input / button 选择器，slot 内的 Element Plus 等控件不受影响。
- `CodeInputRow`：`label` 在行外，行为 `div.ak-code-row.ak-row`（nowrap、底部对齐），输入框 / 按钮 / 图形验证码统一 40px。Register / Reset / ChangeEmail / ProfileFields / Login 图形码 / WechatQrLogin 绑定视图已改用它。
- 新导出：`AuthShell`、`CodeInputRow`、`ensureShellStyle`、`SHELL_CSS`、`CODE_ROW_CSS`、`detectNative`、`systemLocale`。
- 文案精简（键名不变）：`captchaLoadFailed`、`captchaInvalid`、`alreadyLoggedIn`、微信 `hint` / `unboundHint`。宿主若断言旧文案需更新。

**DOM 变化**：验证码行原为 `<div class="ak-row"><label>验证码<input/></label><button/></div>`，现为 `<div class="ak-field ak-code-field"><label class="ak-field-label"/><div class="ak-code-row ak-row"><input class="ak-input ak-code-input"/><button class="ak-code-btn"/></div></div>`。

**dental 升级需删除的覆盖**（`apps/web/src/App.css`，0.6.0 已内置等价样式，保留会冲突）：
- 约 215–300 行整段 `.ak-row` 修补：`.ak-form/.ak-field/.ak-dialog .ak-row`、`.ak-form .ak-row`、`.ak-row input / .ak-input / > label`、`.ak-row img / button`、`.ak-form .ak-row button`、`.ak-form .ak-row img` 及其 `@media` 内 `.ak-form .ak-row`。
- 约 917 行 `.ak-form .ak-row > label input / .ak-input`（label 已不再包裹 input）。
- `pages/profile/ProfilePage.css` 的 `.dental-profile-ak .ak-row button`（含 `:hover`）如只为高度 / 对齐可删；若是品牌色可改用 `--ak-shell-primary` 或保留。
- 其它 DeleteAccountForm / 两步验证的 `.ak-row` 未改动。

## 0.5.1

修复 SSO 自动建号的账号没有已知密码、无法修改密码的问题。

- `auth.users` 新增 `password_set`（布尔，NOT NULL，默认 `true`）。迁移：`sql/upgrade_0_5_1.sql` / `upgrade_sql("0.5.1")`（幂等）；`ensure_schema` / `init_db` 自动补列。老账号保持 `true`。
- 新增 `account_kit.create_user(...)`：宿主建号（如 SSO），不传 `password` 时存随机密码且 `password_set=False`；也可显式传 `password_set`。
- `POST /change-password`：`password_set=false` 时不校验旧密码，强制邮箱验证码（`send-code` 的 `change_password` 用途），成功后置 `true`。`PATCH /me` 的 `new_password` 同规则。账号无邮箱返回 `PASSWORD_SET_EMAIL_REQUIRED`。
- `POST /reset-password` 成功同样置 `password_set=true`。
- `GET /me` 返回 `password_set`。
- Vue / React `ProfileFields`：`user.password_set === false` 时标题为「设置密码」/ "Set password"，隐藏旧密码，显示邮箱验证码与发送按钮。`ChangePasswordRequest.old_password` 变为可选。向后兼容 0.5.0。

## 0.5.0

可选 OIDC IdP（默认关闭）、关微信时跳过 wechat 表、LoginForm 记住登录。

- 新模块 `account_kit.sso`：Authorization Code + PKCE S256。路由仅 `sso_idp_enabled=True` 时挂载；热关 403 `SSO_DISABLED`。未挂载 404。
- `id_token` / SSO `access_token` 与登录 JWT 隔离：默认 RS256（`sso_signing_key_pem` + JWKS `kid`），可选 HS256（用 client_secret 签）。都不回落 `jwt_secret`。
- 表 `auth.oauth_authorization_codes`。客户端用配置 / `SsoClientConfig.from_env`，不进库、不进 GET。
- authorize 为已登录 Bearer 的 POST（宿主确认页点确认后发码）；`state` 必填原样回传；`redirect_uri` 精确匹配；管理员与无邮箱拒绝。
- token 仅 form；`client_secret_post` / `basic` 不可同时；常量时间比较；code 一次性 60s，重放作废已签出 `jti`。userinfo 拒绝登录 JWT。
- `id_token` 与 userinfo 均含 `email`、`email_verified`、`name`、`preferred_username`、`username`。
- RP 辅助：`discover`（TTL 可注入缓存）、`exchange_authorization_code`、`fetch_userinfo`、`verify_id_token`（iss/aud/exp/nonce/签名）。
- `wechat_enabled=False` 时改密 / 重置 / 删用户不再访问 `auth.wechat_*`，宿主可不建微信表。
- Vue / React `LoginForm`：`defaultUsername` / `defaultPassword`、`beforeSubmit`（返回 `false` 中止）、输入框 `name` / `autocomplete`；React `onSuccess` 第二参带凭据。`sso_links` 不进 kit。

契约：[docs/sso.md](docs/sso.md)。

## 0.4.1

微信 bind-existing 图形验证码与普通登录对齐。

- Vue / React `WechatQrLogin`「绑定已有账号」：服务端开启 captcha 时按 `LoginForm` 同样规则按需显示、点击刷新、校验失败后换图；请求携带 `captcha_id` / `captcha_code`。关闭 captcha 时不显示。
- `POST /login/wechat/bind-existing` 的 captcha 判断、错误码（`CAPTCHA_REQUIRED` / `CAPTCHA_INVALID`）与失败计数（含管理员 `admin_login_captcha_always`、与 `/login` 共用计数器）与 `POST /login` 一致。

## 0.4.0

微信小程序码登录（默认关闭）。

- 新模块 `account_kit.wechat`：网页/App 展示小程序码，医生扫码确认后该端拿到与 `POST /login` 相同形状的 **主会话** token（复用 `complete_login_tokens`）。
- **没有伴生会话。** 不改 JWT、不加 `kind=companion`、不占 `users.current_session_id`。小程序 **不发 JWT**，只用 `wx.login` 换 openid。
- 未绑定：网页 bind-existing（密码；开了 2FA 返回与 `/login` 同形的 401 `MFA_REQUIRED`，`detail` 带 `bind_ticket`，用现有 `POST /login/2fa` 完成后绑定）或 register。也可在 bind-existing 一次带第二因素。
- 设置页 bind / unbind。改密作废未消费 ticket、保留绑定；删用户级联删 identity。
- `session_key` 不落库。`wechat_app_secret` 不出现在任何 GET 配置接口。
- Vue / React 导出 `WechatQrLogin`、`WechatBindSettings`。
- 表：`auth.wechat_identities`、`auth.wechat_login_tickets`。`ensure_schema` / `upgrade_sql("0.4.0")` 可加表。
- 小程序 scan/confirm 的 `ticket` 字段可直接填码里的 `scene`；`purpose` 可选，以服务端票据用途为准；绑定码也可经 `/login/wechat/scan`、`/login/wechat/confirm` 完成。

契约：[docs/wechat.md](docs/wechat.md)。
