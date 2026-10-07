# 配置

宿主通过 `AccountKitConfig` 注入运行时设置。下面只列与后台账号安全相关的项；其余见根 README。

## 单一管理员（无开关）

`is_admin` 只能由宿主写入：直接改库，或调用 kit 导出的 `ensure_admin(db, username, email, password, *, reset_password=False, config=None)`。

- 整个库恰好一名管理员。
- 任何 kit API 都不能改 `is_admin`、不能删除/停用/撤审批管理员、不能产生第二名管理员。
- `PATCH {admin_prefix}/users/{id}` 带 `is_admin` → 400 `ADMIN_FLAG_IMMUTABLE`。
- 停用或把管理员审批改为非 `approved` → 400 `ADMIN_DEACTIVATE_FORBIDDEN`。
- `DELETE {admin_prefix}/users/{id}` 对管理员 → 400 `ADMIN_DELETE_FORBIDDEN`。
- `POST /me/delete` 对管理员 → 400 `ADMIN_SELF_DELETE_FORBIDDEN`（原行为）。

`ensure_admin`：

| 情况 | 结果 |
|---|---|
| 无管理员，用户名和邮箱都空闲 | 创建管理员 |
| 已有同用户名管理员 | 幂等，不改密；`reset_password=True` 时才改密 |
| 已有另一名管理员 | 抛 `AdminSetupError`（`ADMIN_ALREADY_EXISTS`） |
| 用户名或邮箱属于非管理员 | 抛 `ADMIN_USERNAME_TAKEN` / `ADMIN_EMAIL_TAKEN`，不接管 |
| 密码短于 `admin_password_min_length`（`None` 则继承 `password_min_length`） | `PASSWORD_TOO_SHORT` |

数据库有部分唯一索引 `auth.uq_users_single_admin`（`WHERE is_admin = true`）。升级行为见 [upgrade.md](upgrade.md)。

## 登录锁定与限流

| 配置 | 默认 | 说明 |
|---|---|---|
| `login_lockout_attempts` | `0`（关） | 全局逐账号锁定 |
| `login_lockout_seconds` | `900` | 锁定窗口（秒） |
| `admin_login_lockout_attempts` | `5` | 只对 `is_admin`；达到后 429 `ACCOUNT_LOCKED`（`retry_after`） |
| `admin_login_lockout_seconds` | `900` | |
| `login_rate_limit_ip` / `login_rate_limit_user` | `0` | 现有限流，默认关 |
| `admin_login_rate_limit_user` | `0` | 管理员额外按用户名限流；0=只用全局 |
| `admin_login_captcha_always` | `False` | 管理员每次登录要 captcha（需已启用 captcha） |

成功登录会清该账号的 lockout 计数。不存在的用户名仍会跑 dummy bcrypt，避免时序侧信道。

## 管理员 2FA 与会话

| 配置 | 默认 | 说明 |
|---|---|---|
| `admin_require_2fa` | `False` | 未绑 2FA 的管理员可登录、可调 `/2fa/*`，但 `require_admin` 返回 403 `ADMIN_2FA_REQUIRED`。忽略受信设备；登录不能用邮箱码当第二因素 |
| `admin_setup_require_password` | `True` | 管理员 `POST /2fa/setup` 必须带当前密码 |
| `admin_ip_allowlist` | `()` | 空=关；非空则 `require_admin` 校验 `client_ip`，否则 403 `ADMIN_IP_FORBIDDEN` |
| `admin_access_token_expire_minutes` | `None` | `None` 继承 `access_token_expire_minutes`（1440） |
| `admin_refresh_disabled` | `False` | `True` 时管理员登录不发 refresh |
| `admin_password_min_length` | `None` | `None` 继承 `password_min_length`（6）。建议宿主设 12 |
| `audit_admin_login` | `True` | `login_success` / `login_failed` 的 meta 含 `is_admin` |

其它行为（无单独开关）：

- `get_current_user` 不再接受 `?token=`。头像 `GET /users/{id}/avatar` 显式允许 query token。后台路由带 `?token=` 且无 `Authorization` → 401。
- 后续请求校验 `approval_status == approved`，撤审批后 access token 立刻 403。
- 停用或撤审批普通用户时清 `single_device` 会话并吊销 refresh。

## 建议的宿主收紧

现网管理员可能还没开 2FA，所以强制 2FA、更短 TTL、关 refresh、更高密码下限都是 opt-in：

```python
AccountKitConfig(
    jwt_secret="...",
    captcha_builtin=True,  # 或 captcha_verifier
    admin_require_2fa=True,  # 先让现有管理员绑 TOTP 再开
    admin_ip_allowlist=("203.0.113.10",),
    admin_refresh_disabled=True,
    admin_access_token_expire_minutes=60,
    admin_password_min_length=12,
)
```

种子管理员：

```python
from account_kit import ensure_admin

await ensure_admin(session, "ops", "ops@example.com", password)
```
