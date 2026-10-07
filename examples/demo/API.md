# account-kit demo 接口契约（前端唯一依据）

后端：`examples/demo/server/`。account-kit **v0.2.2**。前缀：

| 前缀 | 说明 |
|---|---|
| `/api/setup` | demo 初始化（未配置数据库时的向导） |
| `/api/demo` | 仅 demo：内存信箱 |
| `/api/auth` | kit 用户接口（`AccountKitConfig.api_prefix`） |
| `/api/admin/account` | kit 后台（`AccountKitConfig.admin_prefix`，需 `is_admin`） |

未初始化时，`/api/auth/*` 与 `/api/admin/*` 返回 **503**，`detail.code = NOT_INITIALIZED`。

开发时 Vite 把 `/api` 代理到 `http://127.0.0.1:8000`。生产由本服务托管 `web-vue/dist` 或 `web-react/dist`（`DEMO_WEB=vue|react`），同源，client 的 `baseUrl` 用 `/api/auth`。

鉴权：`Authorization: Bearer <access_token>`。登录、`/login/2fa` 为 **form**（`application/x-www-form-urlencoded`）；其余 JSON，除非注明。

界面包：`createAccountClient("/api/auth", { getToken, logoutPath: "/logout", autoRefresh })`。不要给 admin 调这个 client（它没有后台方法），后台用 `fetch`。

---

## 前端页面清单

请实现这些页面/路由（Vue 与 React 各一份，组件名以界面包导出为准）。

1. **Setup 向导**（`initialized === false` 时强制进入，完成后跳转登录）
   - `GET /api/setup/status`
   - 填 Postgres：`POST /api/setup/test-db`
   - 填管理员 + 功能开关 + 邮件模式：`POST /api/setup/init`
   - 已初始化再提交 → 409 `ALREADY_INITIALIZED`
2. **登录** — `LoginForm` + 需要时 `TwoFactorLoginDialog`（`@mfa` / `onMfa`）。428 时 `LoginForm` 会自己拉验证码。
3. **注册** — `RegisterForm`（先 `sendCode` purpose=`register`）。验证码从站内信箱抄。
4. **找回密码** — `ResetPasswordForm`。
5. **账号页**（需登录）
   - `ProfileFields`（改资料 / 改密，`passwordEmailCode="auto"`）
   - `ChangeEmailForm`（`requirePassword` 默认 true）
   - `TwoFactorSettings`（`language="zh"`，装 peer `qrcode` 或传 `renderQr`）
   - `LogoutButton`（可再做「全部设备」`allDevices`）
   - `DeleteAccountForm`（`twoFactorEnabled`、`emailCodeAvailable` 来自 `twoFactorStatus`）
   - `TierBadge` 可选
6. **后台**（`me.is_admin`）
   - 用户列表 / 审批 / 启停 / 角色等级：`GET/PATCH /api/admin/account/users`
   - 审计日志：`GET /api/admin/account/audit-logs`
   - 可选：角色/等级 CRUD、角色申请审核、`POST .../users/{id}/2fa/reset`
7. **站内信箱**（demo）— `GET /api/demo/outbox`，展示最近验证码，方便注册/改邮/2FA。不要在生产宿主里做这个接口。

令牌：`createTokenStore("account-kit:tokens")` 接到 client：

```ts
const store = createTokenStore("account-kit:tokens")
const client = createAccountClient("/api/auth", {
  getToken: store.getAccessToken,
  logoutPath: "/logout",
  autoRefresh: {
    getRefreshToken: store.getRefreshToken,
    onTokens: store.set,
    onRefreshFailed: store.clear,
  },
})
```

`LoginForm` 的 `@success` / `onSuccess` 第二参带 `{ tokens }`，请 `store.set(tokens)`。受信设备：`getTrustedDeviceToken(trustedDeviceScope("", username))`，登录 2FA 对话框设 `scope`。

未初始化时全站只渲染 Setup。`status.initialized === true` 再进登录。

---

## 错误形

FastAPI `detail` 可能是字符串或对象。对象时看 `detail.code`（界面包 `AccountApiError.code`）。

| HTTP | code | 何时 |
|---|---|---|
| 400 | `DB_UNREACHABLE` / `INIT_FAILED` | setup 连库或建表失败 |
| 409 | `ALREADY_INITIALIZED` | setup 写接口在初始化后 |
| 503 | `NOT_INITIALIZED` | kit 尚未挂载 |
| 401 | `INVALID_CREDENTIALS` | 用户名或密码错（开了 captcha 时；`detail.message` 仍是 `Incorrect username or password`；带 `captcha_required`） |
| 428 | `CAPTCHA_REQUIRED` | 失败次数达阈值，登录必须带图形验证码 |
| 400 | `CAPTCHA_INVALID` | 图形验证码错或已用 |
| 401 | `MFA_REQUIRED` | 已开 2FA，密码对了但还没过第二因素 |
| 401 | `MFA_CHALLENGE_INVALID` / `MFA_TOO_MANY_ATTEMPTS` | challenge 过期或输错太多次 |
| 400 | `MFA_CODE_REQUIRED` / `MFA_CODE_INVALID` | 缺第二因素 / 码错 |
| 409 | `ALREADY_LOGGED_IN` | `session_mode=single_device` 且别的设备在线（可 `force=true`） |
| 401 | `REFRESH_INVALID` / `REFRESH_EXPIRED` / `REFRESH_REUSED` | 刷新令牌 |
| 401 | `SESSION_REPLACED` | 单设备会话被顶 |
| 400 | `EMAIL_VERIFICATION_REQUIRED` | `PATCH /me` 改邮箱未带 `email_code` |
| 400 | `EMAIL_CHANGE_VIA_ENDPOINT` | `profile_email_change=reject` |
| 429 | `EMAIL_CODE_TOO_FREQUENT` | 改邮发码过快（60s） |
| 429 | `RATE_LIMITED` | 发码/登录等限流；`retry_after` 秒，头 `Retry-After` |
| 400 | `ADMIN_SELF_DELETE_FORBIDDEN` | 管理员自助注销（kit 实现是 **400**） |
| 400 | `TWO_FACTOR_NOT_ENABLED` | 未开 2FA 却要邮箱码注销/关 2FA |
| 403 | （字符串）`Admin required` | 非管理员打后台 |
| 403 | （字符串）`账号尚未通过审批` / `User is disabled` | 登录 |
| 404 | `Not found` | 功能开关关掉的路由（refresh / self_delete / captcha / 2FA 邮箱码等） |

未开 captcha 时，密码错误的 `detail` 是字符串 `Incorrect username or password`（客户端靠这句计数）。demo 默认开 captcha，走对象形。

---

## Setup

### `GET /api/setup/status`

始终可调用（初始化后也行）。

```json
{
  "initialized": false,
  "features": null,
  "mail_mode": null,
  "web": "vue",
  "error": null
}
```

初始化后 `initialized` 为 true，`features` / `mail_mode` 为当时保存的值。`web` 来自环境变量 `DEMO_WEB`（`vue`|`react`）。启动连库失败时 `initialized` 可能仍为 false，`error` 为字符串。

### `POST /api/setup/test-db`

Body：

```json
{ "host": "127.0.0.1", "port": 5432, "user": "postgres", "password": "postgres", "database": "akdemo" }
```

`port` 默认 5432。成功 `{ "ok": true }`。连不上 400 `DB_UNREACHABLE`。初始化后 **409**。

### `POST /api/setup/init`

Body：

```json
{
  "db": { "host": "127.0.0.1", "port": 5432, "user": "postgres", "password": "postgres", "database": "akdemo" },
  "admin": { "username": "demo-admin", "email": "admin@example.com", "password": "secret1a" },
  "features": {
    "refresh": true,
    "captcha": true,
    "self_delete": true,
    "two_factor_email": true,
    "require_approval": false,
    "two_factor": true,
    "logout": true,
    "audit_log": true,
    "role_change": true,
    "session_mode": "stateless",
    "captcha_fail_threshold": 3
  },
  "mail_mode": "console",
  "smtp": {
    "host": "127.0.0.1",
    "port": 1025,
    "user": "",
    "password": "",
    "from_email": "demo@example.com",
    "tls": false
  }
}
```

- `admin.password` 至少 6 位。`admin.email` 须是合法邮箱（`user@localhost` 往往校验失败，用带点的域名）。
- `features` 可省略，默认：**refresh / captcha / self_delete / two_factor_email / two_factor / logout / audit_log / role_change 全开**；`require_approval` 默认 **false**（否则注册后不能登录）；`session_mode` 为 `stateless` 或 `single_device`。
- `mail_mode`：`console`（默认，打印 + 站内信箱）或 `smtp`（还要 `smtp.host`；无 user/password 也能发，方便 MailHog）。
- 成功后写 `examples/demo/server/.demo-config.json`（已 gitignore），**不保存管理员密码**；随后在同一进程挂上 kit，**不用重启**。
- 成功：`{ "initialized": true, "admin": { "username", "email" }, "features": {...}, "mail_mode": "console" }`
- 再调用 init 或 test-db → **409** `ALREADY_INITIALIZED`。

---

## 站内信箱（仅 demo）

### `GET /api/demo/outbox`

Query 可选：`email`、`purpose`。

```json
{
  "items": [
    {
      "to": "user1@example.com",
      "purpose": "register",
      "code": "123456",
      "language": "zh",
      "at": "2026-04-08T12:00:00+00:00"
    }
  ]
}
```

最新在前，最多约 50 条。`purpose` 取值见下节验证码。

注册/改邮/2FA 邮箱码请引导用户来这里抄码（console 模式没有真邮件）。

---

## 验证码邮件 purpose

| purpose | 怎么发 |
|---|---|
| `register` | `POST /api/auth/send-code` |
| `reset_password` | 同上 |
| `change_password` | 同上，且必须带当前用户 Bearer；只能发到自己邮箱 |
| `change_email` | `POST /api/auth/me/email/send-code`（发到**新**邮箱） |
| `login_2fa` | `POST /api/auth/login/2fa/email/send` |
| `disable_2fa` | `POST /api/auth/2fa/disable/email-code` |
| `delete_account` | `POST /api/auth/me/delete/email-code` |

`send-code` 只接受前三个 purpose。TTL 5 分钟。同一邮箱同一 purpose 5 分钟内重发 429（字符串「验证码发送频繁，请稍后再试」）。改邮还有 60 秒冷却（对象 `EMAIL_CODE_TOO_FREQUENT`）。

---

## Auth（`/api/auth`）

### 发码 / 校验码 / 注册

`POST /send-code` `{ "email", "purpose": "register"|"reset_password"|"change_password", "language": "zh" }`  
→ `{ "status": "success", "detail": "验证码已发送" }`  
（邮箱已存在时注册 purpose 仍 200，但不发信，防探测。）

`POST /verify-code` `{ "email", "purpose", "code" }`（6 位）  
→ `{ "status": "success", "detail": "验证码有效" }`

`POST /register`

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "secret1",
  "code": "123456",
  "full_name": "Alice",
  "institution": null,
  "gender": "female",
  "birth_year_month": "1990-01",
  "role": null
}
```

`gender`：`male`|`female`。`full_name` 也可写 `real_name`。密码最短 6。  
成功返回用户对象（见「用户对象」）。`require_approval=true` 时 `approval_status` 为 `pending`，登录 403。

### 登录

`POST /login` **form**：

| 字段 | 说明 |
|---|---|
| `username` | 必填 |
| `password` | 必填 |
| `force` | `true` 顶掉单设备会话 |
| `device_name` | 设备名 |
| `trusted_device_token` | 跳过 2FA 的受信设备 |
| `captcha_id` / `captcha_code` | 阈值后必填 |

成功（开了 refresh 时）：

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "refresh_token": "...",
  "refresh_expires_in": 2592000
}
```

关 refresh 则没有后两个字段。

已开 2FA → **401** `MFA_REQUIRED`：

```json
{
  "detail": {
    "code": "MFA_REQUIRED",
    "message": "该账号已开启两步验证，请升级客户端",
    "challenge_token": "...",
    "methods": ["totp", "recovery", "email"],
    "email_available": true,
    "expires_in": 300,
    "trusted_device_days": 30
  }
}
```

`LoginForm` 会 `emit("mfa", challenge)`。接着用 `TwoFactorLoginDialog`。

图形验证码：同一 IP 或用户名在窗口内失败 `captcha_fail_threshold` 次（默认 3）后，再登录不带码 → **428** `CAPTCHA_REQUIRED`。`GET /captcha`：

```json
{ "captcha_id": "...", "image_base64": "<png>", "expires_in": 300 }
```

`image_base64` 无 `data:` 前缀，前端加 `data:image/png;base64,`。一次性。需要 Pillow（demo 已装 `[captcha]`）。

### 第二因素登录

`POST /login/2fa` **form**：`challenge_token` 必填；`code`（TOTP）或 `recovery_code` 或 `email_code` 三选一；`force`、`device_name`、`trust_device`。

成功在登录 token 上额外可能有：`two_factor_method`、`trusted_device_token`、`trusted_device_expires_at`、`recovery_codes_remaining`。

`POST /login/2fa/email/send` JSON `{ "challenge_token", "language": "zh" }`  
→ `{ "status": "success", "email": "al***@example.com", "expires_in": 300, "cooldown": 60 }`  
需要 `two_factor_email`。

### 刷新 / 登出

`POST /refresh` `{ "refresh_token" }` → 新的 `access_token` + `refresh_token` + `refresh_expires_in`。每次轮换。再用旧的 → 401 `REFRESH_REUSED`（整个 family 作废）。界面包 `autoRefresh` 已单飞，不要并行调两次。

`POST /logout`（路径即 `logout_path`，默认 `/logout`）JSON 可空，或 `{ "refresh_token", "all_devices": false }`。始终 `{ "status": "success" }`。过期 token 也 200。

### 当前用户

`GET /me` → 用户对象。

`PATCH /me` 可选字段：`username`、`email`、`full_name`、`institution`、`gender`、`birth_year_month`、`current_password`、`new_password`、`code`、`email_code`。  
改邮箱默认要 `email_code`（先走下面改邮接口或本接口带码）。改密走本接口时要邮箱码；**推荐改密用** `POST /change-password`。

响应：`{ "user": {...}, "access_token": null, "token_type": null }`（改用户名时可能换 token）。

### 改密 / 改邮 / 注销

`POST /change-password` `{ "old_password", "new_password", "code"? }`  
→ `{ "status": "success", "detail": "密码修改成功" }`。demo 默认不要求 `code`。

`POST /me/email/send-code` `{ "new_email", "password"?, "language": "zh" }`  
→ `{ "status": "success", "detail": "验证码已发送", "email": "ne***@...", "expires_in": 300, "cooldown": 60 }`

`POST /me/email` `{ "new_email", "code", "password"? }` → 用户对象。demo 默认要当前密码。

`POST /me/delete` 或 `DELETE /me` `{ "password", "code"?, "recovery_code"?, "email_code"? }`  
→ `{ "status": "success", "mode": "hard"|"soft" }`。开了 2FA 必须再给一个因素。管理员 400 `ADMIN_SELF_DELETE_FORBIDDEN`。

`POST /me/delete/email-code` `{ "language": "zh" }` — 2FA + `two_factor_email` 时发注销码。

### 公开目录

`GET /roles` → `[{ "code", "name", "sort_order", "description", "is_default", "allow_register" }]`（仅 `allow_register`）。  
`GET /tiers` → 等级列表（含 `badge_color`）。  
`RegisterForm` 会自己拉 roles。

`POST /role-change-requests` `{ "requested_role" }`（需登录，且 `role_change` 开）。  
`GET /role-change-requests/me` → pending 或 `null`。

### 用户对象

```json
{
  "id": "uuid",
  "username": "alice",
  "email": "alice@example.com",
  "full_name": null,
  "institution": null,
  "gender": null,
  "birth_year_month": null,
  "role": "user",
  "is_admin": false,
  "is_active": true,
  "approval_status": "approved",
  "has_custom_avatar": false,
  "pending_role": null,
  "tier": "free",
  "tier_name": "免费版",
  "tier_badge_color": "#8c8c8c"
}
```

`approval_status`：`pending`|`approved`|`rejected`。`is_admin` 是后台权限，**不是**角色；角色代码不能叫 `admin`。

---

## 2FA（`/api/auth`，需 `two_factor`）

均需 Bearer，除登录第二步。

| 方法 | 路径 | body / 响应 |
|---|---|---|
| GET | `/2fa/status` | `{ enabled, enabled_at, recovery_codes_remaining, trusted_devices, email_available, trusted_device_days }` |
| POST | `/2fa/setup` | `{ "password" }`（管理员必填；普通用户可选）→ `{ "otpauth_uri", "secret" }` |
| POST | `/2fa/enable` | `{ "code" }` TOTP → `{ "enabled": true, "recovery_codes": ["abcd-efgh", ...] }` **只此一次** |
| POST | `/2fa/disable` | `{ "password", "code"?, "recovery_code"?, "email_code"? }` → `{ "enabled": false }` |
| POST | `/2fa/disable/email-code` | `{ "language": "zh" }` 邮箱码关 2FA |
| POST | `/2fa/recovery-codes/regenerate` | 同 disable 的 password+因素 → `{ "status": "success", "recovery_codes": [...] }` |
| GET | `/trusted-devices` | `{ "devices": [{ "id", "device_name", "created_at", "last_used_at", "expires_at" }] }` |
| DELETE | `/trusted-devices/{id}` | `{ "status": "success" }` |
| DELETE | `/trusted-devices` | `{ "status": "success", "revoked": n }` |

组件：`TwoFactorSettings`、`TwoFactorLoginDialog`。

---

## 后台（`/api/admin/account`，Bearer 且 `is_admin`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/users` | 全部用户（用户对象数组，无分页） |
| PATCH | `/users/{user_id}` | `{ "role"?, "is_active"?, "approval_status"?, "tier_code"? }`。带 `is_admin` 一律 400 `ADMIN_FLAG_IMMUTABLE`；不能停用/撤审批/删除管理员 |
| DELETE | `/users/{user_id}` | 204，删法跟 `user_delete_mode`（demo 默认 hard）；管理员 400 `ADMIN_DELETE_FORBIDDEN` |
| GET | `/roles` | 全部角色 |
| POST | `/roles` | 201，`{ code, name, sort_order, description, is_default, allow_register }` |
| PATCH | `/roles/{code}` | 可改 name/sort_order/description/is_default/allow_register |
| DELETE | `/roles/{code}` | 204 |
| GET/POST/PATCH/DELETE | `/tiers` 同角色；POST 字段含 `badge_color` | |
| POST | `/role-change-requests/{id}/review` | `{ "status": "approved"|"rejected" }` |
| GET | `/audit-logs` | 见下 |
| POST | `/users/{user_id}/2fa/reset` | 204，清 2FA 并吊销 refresh |

### `GET /audit-logs`

Query：`page`（≥1，默认 1）、`page_size`（1–200，默认 50）、`user_id`、`event`（逗号分隔）、`ip`、`since`、`until`。

```json
{
  "items": [
    {
      "id": "uuid",
      "user_id": "uuid|null",
      "event": "login_success",
      "ip": "...",
      "device_name": "...",
      "meta": {},
      "created_at": "ISO-8601"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

事件名：`login_success`、`login_failed`、`login_2fa_failed`、`2fa_enabled`、`2fa_disabled`、`2fa_reset`、`2fa_recovery_regenerated`、`password_changed`、`password_reset`、`email_changed`、`logout`、`refresh_reuse_detected`、`account_deleted`、`verification_code_locked`、`admin_user_updated`、`admin_user_deleted`、`admin_role_changed`、`admin_tier_changed`、`role_change_reviewed`。

---

## 静态托管与开发

- 若存在 `examples/demo/web-vue/dist/index.html`（或 react），服务端托管该目录，未知路径回 `index.html`（SPA）。`/api/*` 不回 HTML。
- `DEMO_WEB=vue|react` 选哪套 dist。
- Vite 开发：

```ts
// vite.config.ts
export default { server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } } }
```

界面包用本地路径，不要配 GitHub Packages token：

```json
{ "dependencies": { "@kqstone/account-ui-vue": "file:../../../packages/account-ui-vue" } }
```

React 包名 `@kqstone/account-ui-react`，组件名相同（另有 `useCountdown`、`CaptchaImageHandle`）。

导出（两包一致，按需引用）：`LoginForm` `RegisterForm` `ResetPasswordForm` `TwoFactorSettings` `TwoFactorLoginDialog` `ProfileFields` `ChangeEmailForm` `DeleteAccountForm` `LogoutButton` `CaptchaImage` `AvatarUploader` `UserAvatar` `TierBadge` `createAccountClient` `createTokenStore` `getMfaChallenge` `getTrustedDeviceToken` `saveTrustedDeviceToken` `clearTrustedDeviceToken` `trustedDeviceScope`。

样式首次渲染注入，class 前缀 `ak-`，不必另引 CSS。文案 `language="zh"`，可用 `labels` 覆盖。
