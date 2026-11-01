# Changelog

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
