# 配置参考 (Configuration Reference)

`account-kit` 通过 `AccountKitConfig` 与 `SmtpConfig` 接收宿主应用的运行时配置。

```python
from account_kit.config import AccountKitConfig, SmtpConfig
```

---

## SmtpConfig 配置项

用于配置内置发信客户端连接的 SMTP 邮件服务器。若宿主提供了自定义 `mailer` 回调，则忽略此配置。

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `host` | `str` | `""` | SMTP 服务器主机地址（如 `smtp.example.com`） |
| `port` | `int` | `587` | SMTP 服务器端口号 |
| `user` | `str` | `""` | SMTP 登录用户名 |
| `password` | `str` | `""` | SMTP 登录密码或授权码 |
| `from_email` | `str` | `""` | 发件人邮箱地址（如 `no-reply@example.com`） |
| `tls` | `bool` | `True` | 是否启用 STARTTLS 加密传输 |

---

## AccountKitConfig 配置项

### 1. 核心与认证令牌

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `jwt_secret` | `str` | *(必填)* | JWT 签名密钥（生产环境请使用强随机字符串） |
| `jwt_algorithm` | `str` | `"HS256"` | JWT 签名与校验算法 |
| `access_token_expire_minutes` | `int` | `1440` | Access Token 有效期（分钟），默认 24 小时 |
| `session_mode` | `str` | `"stateless"` | 会话模式：`"stateless"`（无状态 JWT）或 `"single_device"`（单设备互踢会话） |
| `session_active_hours` | `int` | `12` | 单设备会话空闲失效时长（小时） |
| `secret_key` | `str` | `""` | 验证码与恢复码 HMAC 计算密钥；为空时回退至 `jwt_secret` |
| `file_encryption_key` | `str` | `""` | TOTP 密钥存储的 Fernet 对称加密密钥；为空时依次尝试 `secret_key`、`jwt_secret` |

### 2. 路由与基础策略

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `api_prefix` | `str` | `"/api/auth"` | 公共与用户端接口路由前缀 |
| `admin_prefix` | `str` | `"/api/admin/account"` | 管理员端接口路由前缀 |
| `brand_name` | `str` | `"Account"` | 应用/产品品牌名称，用于邮件展示及 TOTP 发行者标识 |
| `password_min_length` | `int` | `6` | 密码最小字符长度限制 |
| `forbid_admin_like_usernames` | `bool` | `False` | 是否禁止注册包含 `admin` 等敏感字样的用户名 |
| `reserved_usernames` | `Tuple[str, ...]` | `()` | 系统保留不可注册的用户名列表元组 |
| `require_approval` | `bool` | `False` | 是否开启新注册用户需管理员审批后方可登录 |
| `email_domain_restriction` | `bool` | `False` | 是否开启邮箱后缀白名单限制 |
| `allowed_email_domains` | `Tuple[str, ...]` | `()` | 允许注册的邮箱域名后缀元组（如 `("example.com",)`） |
| `role_change_enabled` | `bool` | `False` | 是否允许前台普通用户申请变更所属角色 |

### 3. 状态存储与频控限流

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `state_backend` | `str` | `"db"` | 安全临时状态存储后端：`"db"`（数据库表，跨进程/实例共享）或 `"memory"`（单进程内存） |
| `verify_code_max_attempts` | `int` | `5` | 同一邮箱同一用途验证码最大输错次数；超限将作废该用途所有未消费验证码并锁定 |
| `send_code_rate_limit_ip` | `int` | `10` | 同一 IP 在窗口时间内最多发送验证码次数（0 为不限制） |
| `send_code_rate_limit_email` | `int` | `5` | 同一邮箱在窗口时间内最多接收验证码次数（0 为不限制） |
| `send_code_rate_window_seconds` | `int` | `3600` | 验证码发信限流统计时间窗口（秒，默认 1 小时） |
| `reset_password_rate_limit_ip` | `int` | `10` | 找回密码端点同一 IP 限额（0 为不限制） |
| `reset_password_rate_window_seconds` | `int` | `3600` | 找回密码端点限流窗口（秒） |
| `register_rate_limit_ip` | `int` | `0` | 注册端点同一 IP 限额（0 为不限制） |
| `register_rate_window_seconds` | `int` | `3600` | 注册端点限流窗口（秒） |
| `login_rate_limit_ip` | `int` | `0` | 登录端点同一 IP 限额（0 为不限制） |
| `login_rate_limit_user` | `int` | `0` | 登录端点同一用户名限额（0 为不限制） |
| `login_rate_window_seconds` | `int` | `60` | 登录端点限流窗口（秒） |

### 4. 两步验证 (2FA) 与受信设备

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `two_factor_enabled` | `bool` | `True` | 是否启用 TOTP 两步验证功能 |
| `two_factor_email_enabled` | `bool` | `False` | 是否支持邮箱验证码作为备用第二因素（替代 TOTP 验证器登录或解绑） |
| `two_factor_challenge_ttl_seconds` | `int` | `300` | 登录第二步挑战令牌的有效期（秒） |
| `two_factor_max_attempts` | `int` | `5` | 每个 2FA 登录挑战允许的最大输错次数；超限后挑战作废 |
| `trusted_device_days` | `int` | `30` | 受信任设备 Cookie/Token 的免二次验证有效期（天） |

### 5. 图形验证码 (Captcha)

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `captcha_builtin` | `bool` | `False` | 是否启用内置图形验证码服务（需安装 `account-kit[captcha]`） |
| `captcha_verifier` | `Optional[CaptchaVerifier]` | `None` | 宿主自定义验证码校验器 `fn(id, code) -> bool`（支持同步/异步），若设置则优先于内置验证码 |
| `captcha_fail_threshold` | `int` | `3` | 连续密码错误达到该阈值后强制要求图形验证码 |
| `captcha_fail_window_seconds` | `int` | `900` | 登录失败计数统计时间窗口（秒，默认 15 分钟） |
| `captcha_ttl_seconds` | `int` | `300` | 内置图形验证码有效期（秒） |
| `captcha_length` | `int` | `4` | 内置图形验证码字符长度 |

### 6. 令牌刷新、登出与注销

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `refresh_token_enabled` | `bool` | `False` | 是否启用 Refresh Token 轮换机制（开启后登录返回 refresh_token） |
| `refresh_token_expire_days` | `int` | `30` | 刷新令牌有效期（天） |
| `logout_enabled` | `bool` | `True` | 是否挂载登出端点 |
| `logout_path` | `str` | `"/logout"` | 登出端点子路径（挂载在 `api_prefix` 下） |
| `self_delete_enabled` | `bool` | `False` | 是否允许普通用户自助注销账号 |
| `user_delete_mode` | `str` | `"hard"` | 账号删除模式：`"hard"`（物理删除数据行）或 `"soft"`（软删除，停用账号、匿名化脱敏保留行以满足外键） |

### 7. 个人资料、改密与头像

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `profile_email_change` | `str` | `"verify"` | `PATCH /me` 修改邮箱行为：`"verify"`（必须附带新邮箱验证码及当前密码）、`"reject"`（拒绝在 PATCH 改邮箱，引导至独立端点）、`"direct"`（直接保存，不推荐） |
| `change_email_require_password` | `bool` | `True` | 换绑邮箱端点是否需要验证当前账号密码 |
| `change_password_require_email_code` | `bool` | `False` | `POST /change-password` 端点是否强制要求邮箱验证码 |
| `avatar_enabled` | `bool` | `False` | 是否启用头像上传与管理端点 |
| `avatar_save` | `Optional[AvatarSave]` | `None` | 头像存储异步回调 `async fn(user_id, raw_bytes, content_type, filename) -> storage_key` |
| `avatar_delete` | `Optional[AvatarDelete]` | `None` | 头像删除异步回调 `async fn(storage_key) -> None` |
| `avatar_open` | `Optional[AvatarOpen]` | `None` | 头像读取异步回调 `async fn(storage_key) -> (file_like_or_bytes, media_type)` |

### 8. 邮件模板与服务

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `smtp` | `SmtpConfig` | `SmtpConfig()` | SMTP 发信连接配置实例 |
| `mailer` | `Optional[Mailer]` | `None` | 宿主自定义异步发信回调 `async fn(to, purpose, code, lang)`，设置后接管所有发信 |
| `email_template_dir` | `Optional[str]` | `None` | 宿主自定义 Jinja 模板文件目录路径（优先于内置模板） |
| `email_template_map` | `Optional[EmailTemplateMap]` | `None` | 业务用途 (purpose) 到模板文件名的映射字典（支持 `{lang}` 占位符） |

### 9. 审计与生命周期钩子

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `audit_log_enabled` | `bool` | `True` | 是否将安全事件记录写入 `auth.auth_audit_logs` 表 |
| `on_audit` | `Optional[AuditHook]` | `None` | 审计日志写入完成后的异步回调 `async fn(db, event, user_id, meta)` |
| `client_ip` | `Optional[ClientIp]` | `None` | 自定义客户端真实 IP 解析回调 `fn(request) -> str`（如反代提取真实 IP） |
| `before_login` | `Optional[BeforeLogin]` | `None` | 登录验证前异步钩子 `async fn(request, username)` |
| `before_register` | `Optional[BeforeRegister]` | `None` | 用户注册前异步钩子 `async fn(request)` |
| `before_two_factor` | `Optional[BeforeTwoFactor]` | `None` | 执行 2FA 校验或发信前异步钩子 `async fn(request, user)` |
| `before_send_code` | `Optional[BeforeSendCode]` | `None` | 发送任意验证码邮件前的异步钩子 `async fn(request, email, purpose)`，抛出 HTTPException 可拒绝 |
| `before_action` | `Optional[BeforeAction]` | `None` | 执行敏感操作前的统一异步钩子 `async fn(request, action, info)` |
| `on_registered` | `Optional[UserHook]` | `None` | 用户注册成功后的异步回调 `async fn(db, user)` |
| `on_login` | `Optional[UserHook]` | `None` | 用户登录成功后的异步回调 `async fn(db, user)` |
| `on_password_changed` | `Optional[UserHook]` | `None` | 密码修改成功后的异步回调 `async fn(db, user)` |
| `on_logout` | `Optional[UserHook]` | `None` | 用户退出登录后的异步回调 `async fn(db, user)` |
| `on_deleted` | `Optional[UserHook]` | `None` | 用户账号注销/删除前的异步回调 `async fn(db, user)` |
