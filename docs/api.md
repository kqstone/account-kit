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
- **异常响应**:
  - `401 Unauthorized`: 密码错误，返回 `detail="Incorrect username or password"`；若开启了图形验证码，响应体包含 `{"captcha_required": true}`。
  - `428 Precondition Required`: 密码连续输错达到阈值，要求输入图形验证码。`detail={"code": "CAPTCHA_REQUIRED", "message": "请输入图形验证码", "captcha_required": true}`。
  - `400 Bad Request`: 图形验证码输入错误。`detail={"code": "CAPTCHA_INVALID", "message": "图形验证码错误，请重新输入", "captcha_required": true}`。
  - `403 Forbidden`: 账号已停用 (`"User is disabled"`) 或注册未审批 (`"账号尚未通过审批"`)。
  - `409 Conflict`: 单设备模式下已被其他设备登录。`detail={"code": "ALREADY_LOGGED_IN", "message": "该账号已在其它设备登录", "current_device": "..."}`。
  - `401 Unauthorized (MFA)`: 触发两步验证。`detail={"code": "MFA_REQUIRED", "message": "需要两步验证", "challenge_token": "...", "email_available": bool, "methods": ["totp", "recovery", "email"]}`。

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
| `PATCH` | `/users/{user_id}` | 修改用户状态（角色、等级、is_admin、is_active、审批状态） | - |
| `DELETE` | `/users/{user_id}` | 删除或软删除用户（受 `user_delete_mode` 控制） | - |
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

当接口发生异常时，统一返回符合规范的 JSON 错误响应。业务级错误结构形如：
```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误说明"
  }
}
```

### 核心业务错误码一览表

| 错误码 (code) | HTTP 状态码 | 说明与触发场景 |
| :--- | :--- | :--- |
| `RATE_LIMITED` | 429 | 请求触发安全频控限流，响应头包含 `Retry-After` 秒数 |
| `CAPTCHA_REQUIRED` | 428 | 连续密码错误达到阈值，登录必须输入图形验证码 |
| `CAPTCHA_INVALID` | 400 | 图形验证码校验失败或已过期 |
| `ALREADY_LOGGED_IN` | 409 | 单设备模式下账号已在其他客户端保持会话 |
| `MFA_REQUIRED` | 401 | 账号已开启 2FA，登录需进一步提供第二因素 |
| `MFA_CHALLENGE_INVALID` | 401 | 登录 2FA 挑战已过期或已被销毁，需重新输入密码 |
| `MFA_CODE_REQUIRED` | 400 | 未提供 2FA 验证码或应急恢复码 |
| `MFA_CODE_INVALID` | 400 / 401 | 2FA 验证码错误（附带 `attempts_left` 剩余次数） |
| `MFA_TOO_MANY_ATTEMPTS` | 401 | 2FA 挑战错误次数超限，挑战作废 |
| `REFRESH_INVALID` | 401 | 刷新令牌不存在或已失效 |
| `REFRESH_EXPIRED` | 401 | 刷新令牌已超过有效期 |
| `REFRESH_REUSED` | 401 | 刷新令牌被重放，触发防护已下线全部会话 |
| `SESSION_REPLACED` | 401 | 会话已在其它设备重新登录 |
| `EMAIL_CODE_TOO_FREQUENT` | 429 | 换绑邮箱验证码发送过于频繁（60 秒冷却） |
| `EMAIL_VERIFICATION_REQUIRED`| 400 | 在 `PATCH /me` 修改邮箱时缺少验证码或密码 |
| `EMAIL_CHANGE_VIA_ENDPOINT` | 400 | `profile_email_change="reject"` 时拒绝在 PATCH 改邮箱 |
| `ADMIN_SELF_DELETE_FORBIDDEN` | 403 | 管理员账号禁止执行自助注销操作 |
