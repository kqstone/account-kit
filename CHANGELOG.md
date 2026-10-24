# Changelog

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
