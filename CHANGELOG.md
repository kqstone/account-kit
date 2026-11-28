# Changelog

## Unreleased

发码反馈与同用途重发间隔（服务端）。版本号仍为 0.7.0，发版另行批准。

- 同用途最短重发间隔默认 **120 秒**，可配置：`otp_resend_window_seconds` / `change_email_cooldown_seconds` / `email_code_cooldown_seconds`。IP / 邮箱次数限流与 `OTP_TTL`（5 分钟）不变。
- `POST /send-code` 注册已有账号返回 `400 EMAIL_TAKEN`；重置未注册返回 `404 EMAIL_NOT_REGISTERED`；管理员公开重置返回 `400 PASSWORD_RESET_NOT_ALLOWED`（中性文案）。以上错误路径仍先走 `guard_send`。
- 成功响应补 `cooldown` / `expires_in`（默认 120 / 300）。`EMAIL_CODE_TOO_FREQUENT` 带 `retry_after` 与 `Retry-After`。
- 发出新码时作废同一邮箱同一用途未使用的旧码。空或格式非法的邮箱返回 `400 EMAIL_INVALID`。

套件 UI（Vue / React 同等）：

- 抽出并导出 `PasswordForm`：按 `password_set` 在「设置密码」与「修改密码」间切换；`ProfileFields` 内部复用，不再内嵌第二套密码 UI。
- 全发码入口统一：发送前校验邮箱、按钮「发送中…」锁、仅成功时提示已发送并按接口 `cooldown` 倒计时（缺省 / 回退 **120** 秒）；失败走 `formatError`、不进入成功倒计时。
- `EMAIL_TAKEN` / `EMAIL_NOT_REGISTERED` / `PASSWORD_RESET_NOT_ALLOWED` 如实展示且不倒计时；频率错误用 `retry_after`（无字段回退 120）。倒计时绑定刚发送成功的邮箱，改地址后可向新邮箱发送。

## 0.7.0

审批核心与 SSO bind-ticket 下沉到 kit。未知 SSO 身份不再静默建号；被拒账号错误码从 `ACCOUNT_PENDING` 拆出 `ACCOUNT_REJECTED`。

**破坏性 / 行为变化**

- 拒绝账号登录与拦截返回 `ACCOUNT_REJECTED`（可带 `params.reason`），不再用 `ACCOUNT_PENDING`。过渡期 UI 仍认 `USER_PENDING` / `USER_REJECTED`。
- 未知 SSO 身份（未命中 `sso_links`、邮箱未命中或 `email_verified=false`）**不再** `create_user`。宿主应签发 `bind_ticket`，前端二选一：绑定已有账号 / 创建新账号。
- 邮箱域名限制只约束 **create-account** 与邮箱注册，不约束 bind-existing。
- 默认 `sso_email_auto_link=True`：IdP email 命中本地唯一账号则自动写 link。`email_verified=false` 或缺省不自动关联。
- kit **不**注册 RP 路由、不持有 `sso_links`。实际 URL 由 `AccountClientOptions.ssoPaths` / `adminPrefix` 配置。

**后端**

- `auth.users` 新增 `approval_reason` / `approval_decided_by` / `approval_decided_at`。`auth.bind_tickets` 新表。迁移：`sql/upgrade_0_7_0.sql` / `upgrade_sql("0.7.0")`；`ensure_schema` / `init_db` 幂等。
- `approval.py`：`provision_user`、`assert_login_allowed`、`set_user_approval`、`count_pending`。一个 `require_approval` 同时管邮箱注册、SSO 开户、微信注册。管理员手工建号始终 approved。开关改否不批量放行已有 pending。
- 专用 `PATCH {admin_prefix}/users/{id}/approval`：拒绝必填 1–`approval_reason_max` 字。通用 `PATCH .../users/{id}` 无原因拒绝仍允许（兼容 0.6.0）。`GET .../users?approval_status=`、`GET .../users/pending-count`。
- `bind_ticket.py`：Fernet 一次票，默认 600s；消费 `SELECT FOR UPDATE` + `populate_existing`，避免同 Session 先 load 再锁时读到 identity-map 旧 issued 值。
- `verify_bind_target()`：密码 + captcha + lockout + 审批 + 可选禁管理员 + 2FA。可选 `challenge_token` + 已加载的 `bind_ticket` 行：首次 2FA 通过置 `passed=True` 且 **不 discard**，同一用户同一票后续空码可过（force / reclaim），跨用户/跨票/用途/过期拒绝。宿主绑定+发 token 成功后 `discard_bind_mfa_challenge` / `discard_challenge`。微信 bind-existing 内部改调它（`forbid_admin=False`），不传 `challenge_token` 时原行为不变。
- SSO 邮箱 MFA 挑战挂在 bind_ticket 上：可走 `POST /login/2fa/email/send` 发码；`POST /login/2fa` 若命中 SSO ticket 返回 `SSO_BIND_TICKET_INVALID`，必须二次 POST 宿主 bind-existing（ticket 不消费）。微信仍走 `complete_pending_wechat_bind`。
- 邮件：`approval_approved` / `approval_rejected` / `admin_pending`。SMTP 或 `admin_notify_emails` 空则跳过。Jinja `autoescape` 转义动态 `reason` / `username` / `email`。`provision_user` / `set_user_approval` 仅在 `commit=True` 时 **先 commit 再发信**；`commit=False` 不发，宿主 commit 后调用 `notify_admins_pending` / `notify_user_approval_decision`。`on_pending_user` / `on_approval_decided` 仍在事务内。邮件失败不变成业务失败。
- 审计事件名：`sso_bound` / `sso_unbound` / `login_sso`。
- 被拒重新申请一期不进 kit。

**前端（React / Vue 能力与导出一致）**

- `AccountUser` 审批字段；`formatError` 新码 + 拒绝原因；`RegisterForm` pending 文案；`ApprovalStatusBadge`；`client.admin.setApproval` / `pendingCount`。
- `BindExistingAccountForm`（用户名或邮箱 / 密码 / captcha / 2FA / 错误 / reclaim）。SSO 2FA 把 `challengeToken` 传给宿主；`ALREADY_LOGGED_IN` 强制登录与 `SSO_ORPHAN_PENDING` reclaim 重试同一挑战、免重输 2FA。`client.SsoBindExistingPayload.challengeToken`。
- `SsoBindPanel`：身份摘要、绑定 / 无密码创建、`allowCreate`、倒计时失效、MFA 再 POST 宿主 bind-existing 且保留票、reclaim 确认与冲突。
- `SsoBindSettings`：绑定跳转、邮箱掩码、解绑密码+2FA、`password_set===false` 先设密码门闩。
- `WechatQrLogin` 绑定 Tab 复用共享表单，原 captcha / MFA 行为保留。

**宿主接入要点**

```python
from account_kit.approval import provision_user, assert_login_allowed
from account_kit.bind_ticket import issue_bind_ticket, consume_bind_ticket
from account_kit.bind_target import verify_bind_target

raw, ttl = await issue_bind_ticket(db, get_config(), claims=claims, ip=ip)
user = await verify_bind_target(db, get_config(), request, username=..., password=...)
# 宿主写 sso_links（捕获 IntegrityError）后：
ticket, claims = await consume_bind_ticket(db, raw, config=get_config(), commit=False)
await db.commit()
```

个人中心：解绑前 `password_set` 必须为 true。reclaim 仅当占用方 `pending + password_set=false + approved_at is NULL`；空号不自动删除。

部署后清点历史 pending 空号（`sso_links` 在宿主）：

```sql
SELECT u.id, u.username, u.email, u.approval_status, u.password_set, u.approved_at, l.issuer, l.subject
FROM public.sso_links l
JOIN auth.users u ON u.id = l.user_id
WHERE u.approval_status = 'pending' AND u.password_set = false AND u.approved_at IS NULL;
```

## 0.6.0

新增登录外壳 `AuthShell` 与验证码行 `CodeInputRow`（React / Vue，DOM 与 class 一致），默认文案精简。后端无改动、无迁移。

- `AuthShell`：品牌头（logo / 名称 / 副标题，可点击，`headerAttrs` 透传，如 Tauri `data-tauri-drag-region`）、语言切换、标题卡片、页脚、版权。100dvh 布局，头部 / 卡片头 / 卡片脚固定，仅 `.ak-shell-body` 滚动。`native`（默认 `detectNative()`，识别 Capacitor）隐藏语言切换与版权。`variant="admin"` 走 `--ak-shell-admin-bg`。
- CSS 变量（中性默认值，可在 `:root` / `.ak-shell` / `style` 覆盖）：`--ak-shell-bg`、`--ak-shell-primary`、`--ak-shell-card-bg`、`--ak-shell-card-radius`、`--ak-control-height`（默认 40px）。样式只作用于 `.ak-shell-*` / `.ak-code-*`，不写全局 input / button 选择器，slot 内的 Element Plus 等控件不受影响。
- `CodeInputRow`：`label` 在行外，行为 `div.ak-code-row.ak-row`（nowrap、底部对齐），输入框 / 按钮 / 图形验证码统一 40px。Register / Reset / ChangeEmail / ProfileFields / Login 图形码 / WechatQrLogin 绑定视图已改用它。
- 新导出：`AuthShell`、`CodeInputRow`、`ensureShellStyle`、`SHELL_CSS`、`CODE_ROW_CSS`、`detectNative`、`systemLocale`。
- 文案精简（键名不变）：`captchaLoadFailed`、`captchaInvalid`、`alreadyLoggedIn`、微信 `hint` / `unboundHint`。宿主若断言旧文案需更新。

**DOM 变化**：验证码行原为 `<div class="ak-row"><label>验证码<input/></label><button/></div>`，现为 `<div class="ak-field ak-code-field"><label class="ak-field-label"/><div class="ak-code-row ak-row"><input class="ak-input ak-code-input"/><button class="ak-code-btn"/></div></div>`。

**行为变化（宿主请留意）**
- 默认文案调整：`alreadyLoggedIn`、`captchaInvalid`、`captchaLoadFailed` 及微信 `hint`/`unboundHint`（见各包 `labels.ts`），键名不变，可用 labels 覆盖还原。
- 旧表单验证码行 DOM 改为 CodeInputRow（label 移到行外），控件高度固定 40px（`--ak-control-height`）；`ensureAccountStyle` 会追加注入 `CODE_ROW_CSS`。针对旧 `.ak-row` 结构写自定义样式的宿主可能受影响。

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
