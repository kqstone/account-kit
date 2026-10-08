# API 端点与契约参考 (API Reference)

本文档详细说明 `account-kit` 提供的所有 API 端点、请求/响应结构、行为细节及错误码规范。

路由挂载前缀默认值：
- 用户与公共路由：`{api_prefix}`（默认 `/api/auth`）
- 管理员后台路由：`{admin_prefix}`（默认 `/api/admin/account`）

---

## 目录

1. [认证与会话 (Authentication & Session)](#1-认证与会话)
2. [两步验证 (2FA / MFA)](#2-两步验证)
3. [验证码与密码重置](#3-验证码与密码重置)
4. [个人资料与邮箱管理](#4-个人资料与邮箱管理)
5. [账号注销与头像](#5-账号注销与头像)
6. [角色与等级查询](#6-角色与等级查询)
7. [管理员后台端点](#7-管理员后台端点)
8. [通用错误响应与业务错误码](#8-通用错误响应与业务错误码)

---

## 1. 认证与会话

### 登录 `POST {api_prefix}/login`

用户凭据认证。支持单设备会话控制、登录失败图形验证码触发、两步验证挑战派发。

- **Content-Type**: `application/x-www-form-urlencoded`
- **请求字段**:
  - `username` *(str, 必填)*: 用户名
  - `password` *(str, 必填)*: 密码
  - `force` *(bool, 可选)*: 单设备模式下是否强制顶替已有会话，默认 `false`
  - `device_name` *(str, 可选)*: 设备识别名
  - `trusted_device_token` *(str, 可选)*: 受信设备令牌（若有效可豁免两步验证）
  - `captcha_id` *(str, 可选)*: 图形验证码 ID（当服务端要求时必填）
  - `captcha_code` *(str, 可选)*: 图形验证码内容
- **响应 (200 OK)**:
  ```json
  {
    "access_token": "eyJhbG...",
    "token_type": "bearer",
    "refresh_token": "d8a1...",       // 仅当 refresh_token_enabled=True 时返回
    "refresh_expires_in": 2592000     // 刷新令牌过期秒数
  }
  ```
- **异常响应**（默认 `zh-CN` 文案；`X-Locale: en` 为英文。顶层另有 `code`，见第 8 节）:
  - `401 Unauthorized`: 密码错误。未开 captcha 时 `detail` 为字符串「用户名或密码错误」；开启 captcha 后 `detail` 为对象，含 `captcha_required`。
  - `428 Precondition Required`: 连续密码错误达到阈值。`detail={"code": "CAPTCHA_REQUIRED", "message": "需要图形验证码", "captcha_required": true}`。
  - `400 Bad Request`: 图形验证码错误或已失效。`detail={"code": "CAPTCHA_INVALID", "message": "图形验证码错误或已失效", "captcha_required": true}`。
  - `403 Forbidden`: 账号已停用（「账号已被停用」）或注册未审批（「账号尚未通过审批」）。
  - `409 Conflict`: 单设备模式下已在其他设备登录。`detail={"code": "ALREADY_LOGGED_IN", "message": "该账号已在其他设备登录", "device_name": "..."}`。
  - `401 Unauthorized (MFA)`: 账号已开启两步验证。`detail={"code": "MFA_REQUIRED", "message": "该账号已开启两步验证，请升级客户端", "challenge_token": "...", "email_available": bool, "methods": ["totp", "recovery", "email"]}`。

---

### 轮换刷新令牌 `POST {api_prefix}/refresh`

需开启 `refresh_token_enabled=True`。

- **Content-Type**: `application/json`
- **请求体**: `{"refresh_token": "..."}`
- **响应 (200 OK)**: 返回新的 `access_token` 与轮换后的 `refresh_token`。
- **异常响应**:
  - `401 Unauthorized`:
    - `REFRESH_INVALID`: 令牌不存在或无效。
    - `REFRESH_EXPIRED`: 刷新令牌已过期。
    - `SESSION_REPLACED`: 单设备模式下会话已被新登录顶替。
    - `REFRESH_REUSED`: 检测到已轮换令牌被重复使用（重放攻击）。服务端会立即吊销该令牌家族下的全部令牌，单设备模式下踢下线。

---

### 退出登录 `POST {api_prefix}{logout_path}`

默认路径为 `{api_prefix}/logout`。需开启 `logout_enabled=True`（默认启用）。

- **认证**: 支持可选 Bearer Token（请求头）。
- **请求体 (可选)**: 支持空请求体、JSON 或表单：`{"refresh_token": "...", "all_devices": false}`。
- **行为**:
  - 宽容处理：即使 Access Token 已过期或不存在，接口依然保证返回 `200` 并写入审计日志。
  - 若处于单设备模式且 Token 归属于当前会话，清除当前会话状态。
  - 吊销传入的 `refresh_token` 及其家族；若 `all_devices=true` 且处于认证状态，吊销该用户所有设备的刷新令牌。
- **响应 (200 OK)**: `{"status": "success"}`。

---

### 获取内置图形验证码 `GET {api_prefix}/captcha`

需开启 `captcha_builtin=True` 且安装额外依赖 `account-kit[captcha]`。

- **响应 (200 OK)**:
  ```json
  {
    "captcha_id": "c1f7...",
    "image_base64": "data:image/png;base64,iVBORw0KG...",
    "expires_in": 300
  }
  ```

---

## 2. 两步验证

需启用 `two_factor_enabled=True`（默认开启）。

### 登录两步验证 `POST {api_prefix}/login/2fa`

提交通过第一步认证后获得的 `challenge_token` 以及第二因素。

- **Content-Type**: `application/x-www-form-urlencoded`
- **请求字段**:
  - `challenge_token` *(str, 必填)*: 第一步登录下发的有效挑战标识
  - `code` *(str, 可选)*: TOTP 6 位动态验证码
  - `recovery_code` *(str, 可选)*: 应急恢复备用码
  - `email_code` *(str, 可选)*: 邮箱两步验证码（需开启 `two_factor_email_enabled`）
  - `force` *(bool, 可选)*: 单设备抢占标志
  - `device_name` *(str, 可选)*: 设备识别名
  - `trust_device` *(bool, 可选)*: 是否记住并信任当前设备
- **响应 (200 OK)**:
  ```json
  {
    "access_token": "...",
    "token_type": "bearer",
    "two_factor_method": "totp",
    "trusted_device_token": "...",        // 仅 trust_device=true 时下发
    "trusted_device_expires_at": "...",
    "recovery_codes_remaining": 9,        // 使用恢复码时返回剩余数量
    "refresh_token": "..."
  }
  ```
- **异常响应**:
  - `400 Bad Request`: `MFA_CODE_REQUIRED`（未填写任何验证因素）。
  - `401 Unauthorized`:
    - `MFA_CHALLENGE_INVALID`: 挑战已过期或无效。
    - `MFA_CODE_INVALID`: 验证码错误，响应中附带 `attempts_left` 剩余尝试次数。
    - `MFA_TOO_MANY_ATTEMPTS`: 错误次数达到上限，挑战被强制销毁。

---

### 发送登录 2FA 邮箱验证码 `POST {api_prefix}/login/2fa/email/send`

需开启 `two_factor_email_enabled=True`。

- **Content-Type**: `application/json`
- **请求体**: `{"challenge_token": "...", "language": "zh"}`
- **说明**: 验证密码正确后，可向用户注册邮箱发送登录验证码，用户可作为 `email_code` 提交至 `/login/2fa` 跳过验证器完成登录。

---

### 查询两步验证状态 `GET {api_prefix}/2fa/status`

- **认证**: 需要登录 Bearer Token
- **响应 (200 OK)**:
  ```json
  {
    "enabled": true,
    "enabled_at": "2026-03-01T12:00:00Z",
    "recovery_codes_remaining": 10,
    "trusted_devices": 1,
    "email_available": true,
    "trusted_device_days": 30
  }
  ```

---

### 发起绑定设置 `POST {api_prefix}/2fa/setup`

- **认证**: 需要登录 Bearer Token
- **请求体 (可选)**: `{"password": "当前密码"}`
- **响应 (200 OK)**:
  ```json
  {
    "otpauth_uri": "otpauth://totp/Account:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=Account",
    "secret": "JBSWY3DPEHPK3PXP"
  }
  ```

---

### 激活两步验证 `POST {api_prefix}/2fa/enable`

- **请求体**: `{"code": "123456"}`
- **响应 (200 OK)**: 激活并返回 10 组单次生效的应急恢复码：
  ```json
  {
    "enabled": true,
    "recovery_codes": ["a1b2c3d4", "e5f6g7h8", "..."]
  }
  ```

---

### 关闭两步验证 `POST {api_prefix}/2fa/disable`

- **请求体**: `{"password": "密码", "code": "", "recovery_code": "", "email_code": ""}`
- **说明**: 必须输入当前密码，并提供 TOTP 码、恢复码或邮箱验证码（三选一）。
- **发送关闭 2FA 邮箱码**: `POST {api_prefix}/2fa/disable/email-code`（需 `two_factor_email_enabled=True`）。

---

### 重新生成恢复码 `POST {api_prefix}/2fa/recovery-codes/regenerate`

- **请求体**: `{"password": "密码", "code": "...", "recovery_code": "..."}`
- **响应 (200 OK)**: `{"status": "success", "recovery_codes": [...]}`

---

### 受信设备管理

- `GET {api_prefix}/trusted-devices`: 查看所有已记住的免 2FA 设备列表。
- `DELETE {api_prefix}/trusted-devices/{device_id}`: 吊销指定设备。
- `DELETE {api_prefix}/trusted-devices`: 吊销全部受信设备。

---

## 3. 验证码与密码重置

### 发送通用验证码 `POST {api_prefix}/send-code`

- **请求体**:
  ```json
  {
    "email": "user@example.com",
    "purpose": "register",          // register | reset_password | change_password
    "language": "zh"
  }
  ```
- **说明**:
  - `register`: 邮箱未被注册方可发送；若配置了域名白名单，校验后缀。
  - `reset_password`: 仅当邮箱已注册且非管理员账号时发送。
  - `change_password`: 需要登录态，且发送邮箱必须为当前账号邮箱。
  - 发送受频控与输错防爆破锁定策略保护。

---

### 预校验验证码 `POST {api_prefix}/verify-code`

- **请求体**: `{"email": "...", "purpose": "...", "code": "123456"}`
- **说明**: 校验验证码是否正确且未过期，校验成功但不消耗该验证码。

---

### 注册新账号 `POST {api_prefix}/register`

- **请求体**:
  ```json
  {
    "username": "johndoe",
    "email": "john@example.com",
    "password": "strongpassword",
    "code": "123456",
    "role": "user",
    "full_name": "John Doe",
    "institution": "Org",
    "gender": "male",
    "birth_year_month": "1995-06"
  }
  ```
- **响应 (200 OK)**: 返回注册成功的用户信息。若 `require_approval=True`，用户初始状态为 `approval_status="pending"`，需审批后才可登录。

---

### 找回/重置密码 `POST {api_prefix}/reset-password`

- **请求体**: `{"email": "...", "code": "123456", "new_password": "..."}`
- **响应 (200 OK)**: `{"status": "success", "detail": "密码重置成功"}`

---

## 4. 个人资料与邮箱管理

### 查询当前用户信息 `GET {api_prefix}/me`

- **认证**: 需要登录 Bearer Token
- **响应 (200 OK)**: 返回当前用户的完整 Profile 信息。

---

### 修改个人资料 `PATCH {api_prefix}/me`

- **认证**: 需要登录 Bearer Token
- **请求体**: 支持更新用户名、昵称、性别、机构、新密码、新邮箱等。
- **关于邮箱修改策略 (`profile_email_change`)**:
  - `"verify"` (默认): 若请求体中包含 `email`，必须同时传入 `email_code`（由 `/me/email/send-code` 发送至新邮箱）及 `current_password`，否则返回 `400 EMAIL_VERIFICATION_REQUIRED`。
  - `"reject"`: 禁止在 PATCH 接口修改邮箱，返回 `400 EMAIL_CHANGE_VIA_ENDPOINT`，强制客户端使用专门的 `/me/email` 流程。
  - `"direct"`: 直接更新邮箱，不校验。

---

### 独立修改密码 `POST {api_prefix}/change-password`

- **认证**: 需要登录 Bearer Token
- **请求体**: `{"old_password": "...", "new_password": "...", "code": "..."}`
- **说明**: 默认不强制要求邮箱验证码；若开启 `change_password_require_email_code=True`，则 `code` 必填。修改成功后吊销所有受信设备及刷新令牌。

---

### 换绑邮箱发送验证码 `POST {api_prefix}/me/email/send-code`

- **认证**: 需要登录 Bearer Token
- **请求体**: `{"new_email": "new@example.com", "password": "当前密码", "language": "zh"}`
- **说明**: 验证码发送至新邮箱，且与当前用户 ID 严格绑定。同一用户发送间隔有 60 秒冷却，超频返回 `429 EMAIL_CODE_TOO_FREQUENT`。

---

### 确认换绑邮箱 `POST {api_prefix}/me/email`

- **认证**: 需要登录 Bearer Token
- **请求体**: `{"new_email": "new@example.com", "code": "123456", "password": "当前密码"}`
- **说明**: 成功后更新用户邮箱并记审计日志。

---

## 5. 账号注销与头像

### 自助注销账号 `POST {api_prefix}/me/delete` 或 `DELETE {api_prefix}/me`

需开启 `self_delete_enabled=True`。

- **认证**: 需要登录 Bearer Token
- **请求体**: `{"password": "密码", "code": "...", "recovery_code": "...", "email_code": "..."}`
- **说明**:
  - 管理员账号禁止自助注销，返回 `403 ADMIN_SELF_DELETE_FORBIDDEN`。
  - 若账号开启了两步验证，必须额外提供 TOTP 码、恢复码或注销邮箱验证码（三选一），否则返回 `400 MFA_CODE_REQUIRED`。
  - 发送注销邮箱验证码接口：`POST {api_prefix}/me/delete/email-code`（需 `two_factor_email_enabled=True`）。
  - 注销受 `user_delete_mode` 控制：`"hard"` 物理删除数据行；`"soft"` 软删除（停用、用户名/邮箱墓碑化、清空凭据及头像，保留行记录以维护外键完整性）。

---

### 头像管理

需开启 `avatar_enabled=True` 并配置宿主回调。

- `POST {api_prefix}/me/avatar`: 上传新头像（Multipart `file`）。
- `DELETE {api_prefix}/me/avatar`: 删除当前头像。
- `GET {api_prefix}/users/{user_id}/avatar`: 获取指定用户的头像文件。

---

## 6. 角色与等级查询

- `GET {api_prefix}/roles`: 查询允许用户在注册页面选择的角色列表。
- `GET {api_prefix}/tiers`: 查询公开的用户等级及徽章配置。
- `POST {api_prefix}/role-change-requests`: 需 `role_change_enabled=True`。用户提交角色变更申请：`{"requested_role": "vip"}`。
- `GET {api_prefix}/role-change-requests/me`: 查询当前用户处于 pending 状态的角色变更申请。

---

## 7. 管理员后台端点

挂载前缀为 `{admin_prefix}`（默认 `/api/admin/account`），所有接口均依赖 `require_admin` 鉴权。

| 方法 | 路径 | 说明 | 所需开关 |
| :--- | :--- | :--- | :--- |
| `GET` | `/roles` | 获取系统完整角色目录 | - |
| `POST` | `/roles` | 创建新角色 | - |
| `PATCH` | `/roles/{code}` | 修改角色属性（名称/排序/是否允许注册等） | - |
| `DELETE` | `/roles/{code}` | 删除角色 | - |
| `GET` | `/tiers` | 获取系统等级目录 | - |
| `POST` | `/tiers` | 创建新用户等级 | - |
| `PATCH` | `/tiers/{code}` | 修改等级属性（徽章颜色/排序等） | - |
| `DELETE` | `/tiers/{code}` | 删除用户等级 | - |
| `GET` | `/users` | 查看用户列表（按注册时间倒序） | - |
| `PATCH` | `/users/{user_id}` | 修改用户状态（角色、等级、is_active、审批状态）；不能修改 `is_admin`，也不能停用/撤审批管理员（400） | - |
| `DELETE` | `/users/{user_id}` | 删除或软删除用户（受 `user_delete_mode` 控制）；管理员不可删除（400 `ADMIN_DELETE_FORBIDDEN`） | - |
| `POST` | `/users/{user_id}/2fa/reset` | 管理员强制重置用户的两步验证（清空 TOTP 及受信设备） | `two_factor_enabled` |
| `POST` | `/role-change-requests/{request_id}/review` | 审核角色申请（`{"status": "approved" \| "rejected"}`） | - |
| `GET` | `/audit-logs` | 分页查询系统安全审计日志 | `audit_log_enabled` |

### 审计日志查询参数 (`GET /audit-logs`)
- `page` *(int, 默认 1)*: 分页页码
- `page_size` *(int, 默认 50, 最大 200)*: 分页大小
- `user_id` *(UUID, 可选)*: 过滤指定用户
- `event` *(str, 可选)*: 事件类型，支持逗号分隔多个（如 `login_failed,login_2fa_failed`）
- `ip` *(str, 可选)*: 过滤操作 IP
- `since` / `until` *(ISO 日期时间, 可选)*: 时间范围过滤

---

## 8. 通用错误响应与业务错误码

kit 抛出的 `AccountError` 在 `detail` 之外增加顶层 `code`（有插值时还有 `params`）。`detail` 的类型保持历史形状：字符串仍是字符串，对象仍是对象。宿主 `HTTPException` 不被改写。语言见 [i18n.md](i18n.md)。

字符串形：

```json
{"detail": "用户名或密码错误", "code": "INVALID_CREDENTIALS"}
```

对象形（附加字段在 `detail` 内）：

```json
{
  "detail": {
    "code": "CAPTCHA_REQUIRED",
    "message": "需要图形验证码",
    "captcha_required": true
  },
  "code": "CAPTCHA_REQUIRED"
}
```

下表 `detail` 列为默认形状；开启 captcha 时 `INVALID_CREDENTIALS` 变为对象并带 `captcha_required`。`ADMIN_SELF_DELETE_FORBIDDEN` 是 **400**。`SESSION_REPLACED` 的 `detail` 在两种语言下都是字面量 `SESSION_REPLACED`。

| code | HTTP | detail | 附加字段 | zh-CN | en |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `INVALID_CREDENTIALS` | 401 | string / dict | captcha 开启时 `captcha_required` | 用户名或密码错误 | Incorrect username or password |
| `AUTH_INVALID` | 401 | string | | 登录状态无效，请重新登录 | Could not validate credentials |
| `USER_DISABLED` | 403 | string | | 账号已被停用 | This account has been disabled |
| `ACCOUNT_PENDING` | 403 | string | | 账号尚未通过审批 | This account is pending approval |
| `SESSION_REPLACED` | 401 | string | | `SESSION_REPLACED` | `SESSION_REPLACED` |
| `NOT_FOUND` | 404 | string | | 资源不存在 | Not found |
| `ADMIN_REQUIRED` | 403 | string | | 需要管理员权限 | Admin required |
| `INVALID_PURPOSE` | 400 | string | | 用途无效 | Invalid purpose |
| `ALREADY_LOGGED_IN` | 409 | dict | `device_name` | 该账号已在其他设备登录 | This account is already signed in on another device |
| `ACCOUNT_LOCKED` | 429 | dict | `retry_after`；头 `Retry-After` | 登录失败次数过多，请稍后再试 | Too many failed sign-in attempts, please try again later |
| `RATE_LIMITED` | 429 | dict | `retry_after`；发信文案可用 `SEND_CODE_RATE_LIMITED` | 请求过于频繁，请稍后再试 | Too many requests, please try again later |
| `CAPTCHA_REQUIRED` | 428 | dict | `captcha_required` | 需要图形验证码 | Captcha required |
| `CAPTCHA_INVALID` | 400 | dict | `captcha_required` | 图形验证码错误或已失效 | Captcha is wrong or expired |
| `CAPTCHA_DEPENDENCY_MISSING` | 501 | string | | 图形验证码需要 Pillow：`pip install "account-kit[captcha]"` | Image captcha needs Pillow: … |
| `USERNAME_INVALID` | 400 | string | | 用户名无效 | Invalid username |
| `USERNAME_RESERVED` | 400 | string | | 用户名不可用 | This username is not available |
| `USERNAME_ADMIN_LIKE` | 400 | string | | 用户名不能包含管理员相关字符 | Username must not contain admin-related words |
| `USERNAME_TAKEN` | 400 | string | | 该用户名已注册 | Username already registered |
| `PASSWORD_TOO_SHORT` | 400 | string / dict | setup 路径为 dict | 密码过短 | Password is too short |
| `PASSWORD_TOO_LONG` | 400 | string | | 密码过长 | Password is too long |
| `PASSWORD_INCORRECT` | 400 | string | | 当前密码错误 | Current password is incorrect |
| `OLD_PASSWORD_INCORRECT` | 400 | string | | 旧密码错误 | Current password is incorrect |
| `PASSWORD_REQUIRED` | 400 | dict | | 管理员开启两步验证需要当前密码 | Admins must enter the current password to turn on two-factor authentication |
| `EMAIL_TAKEN` | 400 | string | | 该邮箱已注册 | Email already registered |
| `EMAIL_INVALID` | 400 | string | | 邮箱无效 | Invalid email |
| `EMAIL_UNCHANGED` | 400 | string | | 新邮箱与当前邮箱相同 | New email is the same as the current email |
| `EMAIL_MISMATCH` | 400 | string | | 只能向当前账号邮箱发送验证码 | Codes can only be sent to this account's email |
| `EMAIL_DOMAIN_NOT_ALLOWED` | 400 | string | `params.allowed` | 仅允许带有以下后缀的邮箱注册: {allowed} | Only email addresses ending with the following domains may register: {allowed} |
| `EMAIL_DOMAIN_NOT_ALLOWED_CHANGE` | 400 | string | `params.allowed` | 仅允许使用以下后缀的邮箱: {allowed} | Only email addresses ending with the following domains are allowed: {allowed} |
| `EMAIL_NOT_REGISTERED` | 404 | string | | 该邮箱未注册账号 | No account is registered with this email |
| `EMAIL_CHANGE_VIA_ENDPOINT` | 400 | dict | | 请通过 POST /me/email 修改邮箱 | Change email via POST /me/email |
| `EMAIL_VERIFICATION_REQUIRED` | 400 | dict | | 修改邮箱需要新邮箱收到的验证码 | Changing email requires the code sent to the new address |
| `EMAIL_CODE_REQUIRED` | 400 | dict | `email_code_required` | 请输入邮箱验证码 | Please enter the email verification code |
| `EMAIL_CODE_TOO_FREQUENT` | 429 | dict | | 验证码发送频繁，请稍后再试 | Codes sent too often, please try again later |
| `EMAIL_CODE_INVALID` | 400 | dict | | 邮箱验证码错误或已失效 | Email code is wrong or expired |
| `EMAIL_CODE_LOCKED` | 400 | dict | | 验证码错误次数过多，请重新获取验证码 | Too many wrong codes, please request a new one |
| `EMAIL_UNAVAILABLE` | 400 | dict | | 邮箱验证不可用 | Email verification is not available |
| `CODE_INVALID` | 400 | string | | 验证码错误或已失效 | The code is wrong or expired |
| `CODE_LOCKED` | 400 | string | | 验证码错误次数过多，请重新获取验证码 | Too many wrong codes, please request a new one |
| `MFA_REQUIRED` | 401 | dict | `challenge_token`, `email_available`, `methods` | 该账号已开启两步验证，请升级客户端 | This account has two-factor authentication; please upgrade your client |
| `MFA_CHALLENGE_INVALID` | 401 | dict | | 登录验证已过期，请重新输入密码登录 | Sign-in verification expired, please enter your password again |
| `MFA_CODE_REQUIRED` | 400 | dict | 注销路径文案「请输入两步验证码」 | 请输入验证码 | Please enter the code |
| `MFA_CODE_INVALID` | 400 | dict | `attempts_left`；恢复码文案「恢复码错误」 | 验证码错误 | Incorrect code |
| `MFA_TOO_MANY_ATTEMPTS` | 401 | dict | | 验证码错误次数过多，请重新登录 | Too many wrong codes, please sign in again |
| `MFA_ALREADY_VERIFIED` | 400 | dict | | 已完成验证 | Already verified |
| `TWO_FACTOR_SETUP_REQUIRED` | 400 | string | | 请先开始设置两步验证 | Start two-factor setup first |
| `TWO_FACTOR_NOT_ENABLED` | 400 | dict / string | | 两步验证未开启 | Two-factor authentication is not on |
| `DEVICE_NOT_FOUND` | 404 | dict | | 设备不存在 | Device not found |
| `REFRESH_INVALID` | 401 | dict | | 登录已失效，请重新登录 | Session expired, please sign in again |
| `REFRESH_EXPIRED` | 401 | dict | | 登录已过期，请重新登录 | Session expired, please sign in again |
| `REFRESH_REUSED` | 401 | dict | | 检测到登录凭证被重复使用，已强制下线，请重新登录 | A refresh token was reused; you have been signed out. Please sign in again |
| `ADMIN_DELETE_FORBIDDEN` | 400 | dict | | 不能删除管理员账号 | Cannot delete an admin account |
| `ADMIN_SELF_DELETE_FORBIDDEN` | 400 | dict | | 管理员账号不能自助注销 | Admin accounts cannot delete themselves |
| `ADMIN_FLAG_IMMUTABLE` | 400 | dict | | 管理员标记只能由宿主写入，接口不能修改 | is_admin can only be written by the host, not this API |
| `ADMIN_DEACTIVATE_FORBIDDEN` | 400 | dict | | 不能停用管理员账号 | Cannot deactivate an admin account |
| `ADMIN_IP_FORBIDDEN` | 403 | string | | 当前网络地址不在管理员白名单 | This IP is not on the admin allowlist |
| `ADMIN_2FA_REQUIRED` | 403 | string | | 管理员必须先启用两步验证 | Admins must enable two-factor authentication first |
| `ADMIN_EMAIL_2FA_FORBIDDEN` | 400 | dict | | 管理员不能使用邮箱验证码作为登录第二因素 | Admins cannot use an email code as the login second factor |
| `ADMIN_ALREADY_EXISTS` | 400 | dict | | 已存在管理员账号 | An admin account already exists |
| `ADMIN_USERNAME_TAKEN` | 400 | dict | | 该用户名已存在且不是管理员，拒绝接管 | This username exists and is not admin; takeover refused |
| `ADMIN_EMAIL_TAKEN` | 400 | dict | | 该邮箱已被占用 | This email is already in use |
| `ROLE_RESERVED` | 400 | string | | “管理员”不是角色，请使用后台管理员标记 | admin is not a role; use the backend admin flag |
| `ROLE_CODE_TOO_LONG` | 400 | string | | 角色代码过长 | Role code is too long |
| `ROLE_INVALID` | 400 | string | | 角色无效 | Invalid role |
| `ROLE_EXISTS` | 409 | string | | 角色已存在 | Role already exists |
| `ROLE_NOT_FOUND` | 400 / 404 | string | | 角色不存在 | Role not found |
| `ROLE_DEFAULT_REQUIRED` | 400 | string | | 请先把另一个角色设为默认 | Set another role as default first |
| `ROLE_DEFAULT_DELETE` | 400 | string | | 不能删除默认角色 | Cannot delete the default role |
| `ROLE_IN_USE` | 409 | string | | 仍有用户使用该角色 | The role is still assigned to users |
| `ROLE_UNCHANGED` | 400 | string | | 已经是该角色 | Already this role |
| `ROLE_CHANGE_PENDING` | 409 | string | | 已有待审核的角色申请 | A pending role-change request already exists |
| `ROLE_CHANGE_NOT_FOUND` | 404 | string | | 申请不存在 | Request not found |
| `TIER_CODE_INVALID` | 400 | string | | 等级代码无效 | Invalid tier code |
| `TIER_EXISTS` | 409 | string | | 等级已存在 | Tier already exists |
| `TIER_NOT_FOUND` | 400 / 404 | string | | 等级不存在 | Tier not found |
| `TIER_DEFAULT_REQUIRED` | 400 | string | | 请先把另一个等级设为默认 | Set another tier as default first |
| `TIER_DEFAULT_DELETE` | 400 | string | | 不能删除默认等级 | Cannot delete the default tier |
| `TIER_IN_USE` | 409 | string | | 仍有用户属于该等级 | The tier is still assigned to users |
| `USER_NOT_FOUND` | 404 | string | | 用户不存在 | User not found |
| `USER_ID_INVALID` | 400 | string | | 用户编号无效 | Invalid user_id |
| `STATUS_INVALID` | 400 | string | | 状态无效 | Invalid status |
| `GENDER_INVALID` | 400 | string | | 性别无效 | Invalid gender |
| `BIRTH_FORMAT_INVALID` | 400 / 422 | string | 422 来自 pydantic 校验 | 出生年月格式无效 | Invalid birth year-month format |
| `BIRTH_IN_FUTURE` | 400 / 422 | string | | 出生年月不能晚于当前月份 | Birth year-month cannot be after the current month |
| `BIRTH_INVALID` | 400 / 422 | string | | 出生年月无效 | Invalid birth year-month |
| `AVATAR_DISABLED` | 501 | string | | 头像功能未启用 | Avatars are not enabled |
| `AVATAR_NOT_FOUND` | 404 | string | | 头像不存在 | Avatar not found |
| `AVATAR_STORAGE_UNCONFIGURED` | 501 | string | | 头像存储未配置 | Avatar storage is not configured |
| `AVATAR_EMPTY` | 400 | string | | 请选择头像图片 | Please choose an avatar image |
| `AVATAR_TOO_LARGE` | 400 | string | | 头像不能超过 2MB | Avatar must not exceed 2MB |
| `VALIDATION_ERROR` | 422 | list | 仅 `localize_validation=True` 时顶层带 `code` | 请求参数无效 | Invalid request |

成功 `StatusResponse.detail`：`CODE_SENT`「验证码已发送」、`CODE_VALID`「验证码有效」、`PASSWORD_RESET_OK`「密码重置成功」、`PASSWORD_CHANGED_OK`「密码修改成功」。邮件主题/动作见目录 `EMAIL_SUBJECT_*` / `EMAIL_ACTION_*`。
