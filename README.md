# account-kit

[![PyPI Version](https://img.shields.io/pypi/v/account-kit.svg)](https://pypi.org/project/account-kit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

通用、可复用的 **FastAPI + PostgreSQL** 异步账号与认证库（基于 SQLAlchemy 2.0 + asyncpg，数据表统一置于 `auth` schema，用户主键为 UUID）。配套开箱即用的 Vue 3 与 React 界面组件包：`@kqstone/account-ui-vue`、`@kqstone/account-ui-react`。

> **边界划分**：`account-kit` 专注提供账号注册、认证鉴权、安全凭据维护、两步验证与用户目录等通用账号基础能力；宿主应用的业务限额、积分/会员权益规则、业务接口级频控限流等请在宿主应用中实现。

---

## 功能列表 (0.2.2)

- **核心认证**：账号密码注册与登录、邮箱验证码流转、管理员注册审批机制、单设备互踢会话模式 (`single_device`)、自定义业务角色与用户等级目录、后台管理员权限 (`is_admin`) 隔离。
- **两步验证 (2FA / MFA)**：基于 TOTP 标准的时间戳动态口令、应急备用恢复码、受信设备免验证保持、邮箱验证码作为备用第二因素（用于免验证器登录或紧急解绑）。
- **图形验证码 (Captcha)**：连续登录失败自动触发验证码拦截，支持宿主自定义校验服务或开箱即用的内置图形验证码。
- **防爆破与频控限流**：验证码输错上限熔断与失效锁定机制，全站验证码发信、密码重置、登录端点 IP 与用户维度的滑动窗口频控。
- **账号与资料安全**：换绑邮箱强制新邮箱验证码验证、刷新令牌 (Refresh Token) 家族轮换与重放检测惩罚、标准注销登录端点、用户自助注销账号（支持硬删除与脱敏软删除）。
- **安全审计与扩展**：独立事务记录的关键安全审计日志与后台查询、用户头像管理回调、Jinja2 邮件模板按用途覆盖机制、安全临时状态后端存储（支持跨进程/实例共享的 `db` 模式及单进程 `memory` 模式）。

---

## 安装

### Python 后端包

从 [PyPI](https://pypi.org/project/account-kit/) 安装：

```bash
# 基础核心包
pip install account-kit

# 若需要使用内置图形验证码功能（包含 Pillow 图像处理依赖）
pip install "account-kit[captcha]"
```

### 前端界面组件包

配套的前端界面组件发布于 **GitHub Packages**。在项目根目录下配置 `.npmrc` 文件：

```ini
@kqstone:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NPM_TOKEN}
```

- 本地安装时，`NPM_TOKEN` 需配置具备 `read:packages` 权限的 Personal Access Token (Classic PAT)。
- 在 CI/CD（如 GitHub Actions）中，若使用默认的 `GITHUB_TOKEN`，需预先在包管理页面的 **Manage Actions access** 中为你的消费仓库授权 Read 访问权限。

安装对应的框架包：

```bash
# Vue 3 项目
npm install @kqstone/account-ui-vue

# React 18 / 19 项目
npm install @kqstone/account-ui-react
```

---

## 快速开始

以下为最小可运行的 FastAPI 应用示例：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from account_kit import ensure_schema, ensure_schema_sync, init_db, mount_account, seed_defaults
from account_kit.config import AccountKitConfig, SmtpConfig

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/my_app"

engine = create_async_engine(DATABASE_URL)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with session_factory() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 自动创建 auth schema 及相关数据表（幂等安全，亦可使用 ensure_schema）
    await init_db(engine)
    # 初始化预置角色 (user) 与等级 (free, pro)
    async with session_factory() as session:
        await seed_defaults(session)
    yield
    await engine.dispose()


app = FastAPI(title="My App", lifespan=lifespan)

# 配置并挂载账号系统
config = AccountKitConfig(
    jwt_secret="your-secure-jwt-secret-key",
    brand_name="MyApp",
    # 可选：配置真实发信邮箱
    # smtp=SmtpConfig(host="smtp.example.com", port=587, user="no-reply@example.com", password="pwd", from_email="no-reply@example.com"),
)

mount_account(app, get_db, config)
```

启动应用后，认证路由将自动挂载至 `/api/auth`，后台管理路由将挂载至 `/api/admin/account`。

---

## 配置参考

宿主应用在初始化时向 `mount_account` 传入 `AccountKitConfig`。下表列出最常用的核心配置项：

| 配置项 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `jwt_secret` | *(必填)* | JWT 签名密钥（生产环境请务必保持保密且随机） |
| `session_mode` | `"stateless"` | 会话模式：`"stateless"`（无状态令牌）或 `"single_device"`（单设备互踢） |
| `require_approval` | `False` | 新用户注册是否需管理员在后台审批通过后方可登录 |
| `state_backend` | `"db"` | 安全临时状态存储：`"db"`（写入数据库，支持多进程共享）或 `"memory"` |
| `refresh_token_enabled` | `False` | 是否启用 Refresh Token 轮换与无感刷新机制 |
| `two_factor_enabled` | `True` | 是否启用 TOTP 两步验证能力 |
| `two_factor_email_enabled` | `False` | 是否允许通过邮箱验证码作为登录第二因素（跳过验证器） |
| `captcha_builtin` | `False` | 是否启用内置图形验证码接口（需安装 `account-kit[captcha]`） |
| `logout_enabled` | `True` | 是否挂载注销登录端点（默认路径 `/logout`） |
| `self_delete_enabled` | `False` | 是否允许普通用户自助注销账号 |
| `user_delete_mode` | `"hard"` | 账号删除模式：`"hard"`（物理删除）或 `"soft"`（数据脱敏软删除） |
| `audit_log_enabled` | `True` | 是否将登录、改密、2FA 变更等敏感事件记入审计日志表 |
| `api_prefix` | `"/api/auth"` | 用户端与公共端点挂载前缀 |
| `admin_prefix` | `"/api/admin/account"` | 管理员端点挂载前缀 |

完整的 70+ 项配置与 `SmtpConfig` 详细说明，请参阅完整文档：[docs/configuration.md](docs/configuration.md)。

---

## API 端点概览

路由挂载前缀默认为 `{api_prefix}`（`/api/auth`）与 `{admin_prefix}`（`/api/admin/account`）。

### 用户与公共端点

| 方法 | 路径 | 说明 | 所需配置开关 |
| :--- | :--- | :--- | :--- |
| `POST` | `{api_prefix}/login` | 用户名密码登录（支持单设备、图形验证码与 2FA） | - |
| `POST` | `{api_prefix}/send-code` | 发送邮箱验证码（注册/找回密码/改密） | - |
| `POST` | `{api_prefix}/verify-code` | 预校验邮箱验证码有效性 | - |
| `POST` | `{api_prefix}/register` | 用户注册 | - |
| `POST` | `{api_prefix}/reset-password` | 通过验证码重置密码 | - |
| `POST` | `{api_prefix}/refresh` | 轮换刷新令牌换取新的 Access Token | `refresh_token_enabled` |
| `POST` | `{api_prefix}{logout_path}` | 退出登录（吊销会话及刷新令牌，默认 `/logout`） | `logout_enabled` |
| `GET` | `{api_prefix}/captcha` | 获取内置图形验证码图片与 ID | `captcha_builtin` |
| `GET` | `{api_prefix}/me` | 获取当前登录用户详细资料 | - |
| `PATCH` | `{api_prefix}/me` | 更新用户资料（修改邮箱默认要求验证码） | - |
| `POST` | `{api_prefix}/change-password` | 独立修改密码端点（校验旧密码） | - |
| `POST` | `{api_prefix}/me/email/send-code`| 向新邮箱发送换绑验证码 | - |
| `POST` | `{api_prefix}/me/email` | 验证并确认换绑邮箱 | - |
| `POST` | `{api_prefix}/me/delete` / `DELETE` | 自助注销账号（需密码；开启 2FA 需提供第二因素） | `self_delete_enabled` |
| `POST` | `{api_prefix}/me/delete/email-code` | 发送用于账号注销的邮箱验证码 | `self_delete_enabled` + `two_factor_email_enabled` |
| `POST` | `{api_prefix}/me/avatar` | 上传个人头像 | `avatar_enabled` |
| `DELETE` | `{api_prefix}/me/avatar` | 删除个人头像 | `avatar_enabled` |
| `GET` | `{api_prefix}/users/{user_id}/avatar` | 获取指定用户头像 | `avatar_enabled` |
| `GET` | `{api_prefix}/roles` | 获取公开注册可选的角色列表 | - |
| `GET` | `{api_prefix}/tiers` | 获取公开的用户等级目录 | - |
| `POST` | `{api_prefix}/role-change-requests` | 提交角色变更申请 | `role_change_enabled` |
| `GET` | `{api_prefix}/role-change-requests/me` | 查询当前用户未决的角色申请 | `role_change_enabled` |

### 两步验证 (2FA) 端点

需开启 `two_factor_enabled=True`（默认开启）。

| 方法 | 路径 | 说明 | 所需配置开关 |
| :--- | :--- | :--- | :--- |
| `GET` | `{api_prefix}/2fa/status` | 查询两步验证状态与剩余恢复码数量 | - |
| `POST` | `{api_prefix}/2fa/setup` | 获取 TOTP 密钥与绑定二维码 URI | - |
| `POST` | `{api_prefix}/2fa/enable` | 提交 TOTP 码激活 2FA，并获取 10 组恢复码 | - |
| `POST` | `{api_prefix}/2fa/disable` | 关闭 2FA（需当前密码 + 验证码/恢复码/邮箱码） | - |
| `POST` | `{api_prefix}/2fa/disable/email-code` | 发送用于关闭 2FA 的邮箱验证码 | `two_factor_email_enabled` |
| `POST` | `{api_prefix}/2fa/recovery-codes/regenerate` | 重新生成恢复码 | - |
| `GET` | `{api_prefix}/trusted-devices` | 查询当前用户的受信任免密设备列表 | - |
| `DELETE` | `{api_prefix}/trusted-devices/{device_id}` | 吊销指定的受信任设备 | - |
| `DELETE` | `{api_prefix}/trusted-devices` | 吊销全部受信任设备 | - |
| `POST` | `{api_prefix}/login/2fa` | 登录第二步验证（提交 TOTP/恢复码/邮箱码） | - |
| `POST` | `{api_prefix}/login/2fa/email/send` | 登录时向邮箱发送一次性第二因素验证码 | `two_factor_email_enabled` |

### 管理员后台端点

需具备管理员权限 (`is_admin=True`)。

| 方法 | 路径 | 说明 | 所需配置开关 |
| :--- | :--- | :--- | :--- |
| `GET` / `POST` | `{admin_prefix}/roles` | 查询/创建角色 | - |
| `PATCH` / `DELETE` | `{admin_prefix}/roles/{code}` | 修改/删除指定角色 | - |
| `GET` / `POST` | `{admin_prefix}/tiers` | 查询/创建用户等级 | - |
| `PATCH` / `DELETE` | `{admin_prefix}/tiers/{code}` | 修改/删除指定等级 | - |
| `GET` | `{admin_prefix}/users` | 分页/全量查询用户列表 | - |
| `PATCH` | `{admin_prefix}/users/{user_id}` | 后台修改用户信息（角色、等级、审批、状态等） | - |
| `DELETE` | `{admin_prefix}/users/{user_id}` | 删除或软删除用户 | - |
| `POST` | `{admin_prefix}/users/{user_id}/2fa/reset` | 管理员强制重置用户 2FA | `two_factor_enabled` |
| `POST` | `{admin_prefix}/role-change-requests/{id}/review` | 审批角色变更申请 | - |
| `GET` | `{admin_prefix}/audit-logs` | 分页检索安全审计日志 | `audit_log_enabled` |

接口传参、完整响应格式及业务错误码规范请阅读：[docs/api.md](docs/api.md)。

---

## 界面组件概览

`@kqstone/account-ui-vue` (Vue 3) 与 `@kqstone/account-ui-react` (React 18/19) 提供统一的组件能力与样式封装：

### 核心 UI 组件

| 组件名 | 说明 |
| :--- | :--- |
| `LoginForm` | 账号密码登录表单，内置图形验证码拦截与 2FA 挑战引导 |
| `RegisterForm` | 用户注册表单，支持发送验证码与角色选择 |
| `ResetPasswordForm` | 密码找回与重置表单 |
| `TwoFactorSettings` | 2FA 管理面板（TOTP 绑定向导、二维码展示、恢复码生成、受信设备列表） |
| `TwoFactorLoginDialog` | 登录双因素验证弹窗（支持 TOTP 动态码、恢复码与邮箱备用码） |
| `ChangeEmailForm` | 换绑邮箱独立表单（向新邮箱发码、安全冷却与密码核验） |
| `DeleteAccountForm` | 自助注销账号表单（密码确认及 2FA 第二因素校验） |
| `ProfileFields` | 个人资料信息展示与编辑字段（支持改密邮箱验证码模式） |
| `AvatarUploader` | 头像上传与更新组件 |
| `UserAvatar` | 用户头像展示组件（支持性别默认占位与图片加载兜底） |
| `CaptchaImage` | 图形验证码图片展示与点击刷新组件 |
| `TierBadge` | 用户等级/会员徽章标签组件 |
| `LogoutButton` | 快捷登出按钮，自动清空本地会话并调用服务端注销接口 |

### 客户端工具与 Token 管理

界面包内置了请求客户端 `createAccountClient` 与令牌管理器 `createTokenStore`，支持 401 单飞（Single Flight）自动轮换 Token 与请求无感重试：

```ts
import { createAccountClient, createTokenStore } from "@kqstone/account-ui-vue" // 或 @kqstone/account-ui-react

// 1. 创建本地令牌存储器（默认基于 localStorage）
const tokenStore = createTokenStore("my-app:tokens")

// 2. 初始化 API 客户端并配置 401 自动无感刷新
const client = createAccountClient("/api/auth", {
  getToken: () => tokenStore.getAccessToken(),
  autoRefresh: {
    getRefreshToken: () => tokenStore.getRefreshToken(),
    onTokens: (tokens) => tokenStore.set(tokens),
    onRefreshFailed: () => tokenStore.clear(),
  },
})

// 3. 发起调用（需传入 access token）
const user = await client.me(tokenStore.getAccessToken()!)
```

---

## 升级说明 (0.2.1 → 0.2.2)

从 0.2.1 升级至 0.2.2 的必做注意事项：

1. **数据库补齐 4 张新表**：新增了限流计数、2FA 挑战、刷新令牌和图形验证码表。启动时调用 `await ensure_schema(engine)`，或在数据库执行 `sql/upgrade_0_2_2.sql`（可调 `upgrade_sql("0.2.2")` 读取）。
2. **`PATCH /me` 修改邮箱默认需验证**：默认 `profile_email_change="verify"`。若请求中提交 `email` 必须携带验证码与密码；前端需适配换绑流程，或在服务端显式设置 `profile_email_change="direct"` 过渡。
3. **状态存储默认切为数据库**：`state_backend="db"` 为默认值，安全计数跨进程/实例共享。单元测试若需快速重置计数，建议配置为 `state_backend="memory"`。
4. **内置注册 `/logout` 端点**：kit 默认注册注销路由，若宿主应用在 `mount_account` 之后挂载了相同路径的路由，请注意避免冲突或设置 `logout_enabled=False`。
5. **底层内部 API 异步化**：`mfa_required`、`captcha.*` 及 2FA 挑战读写方法已调整为 `async` 并要求传入 `db` 参数。

查看包含 0.2.0 与 0.2.2 的完整演进说明，请参阅：[docs/upgrade.md](docs/upgrade.md)。

---

## 示例应用

仓库内置了免 Docker 依赖、开箱即用的官方全功能演示程序（包含配置向导、站内虚拟信箱、前后端集成）：

- 演示项目说明与操作指南：[examples/demo/README.md](examples/demo/README.md)
- 演示接口契约：[examples/demo/API.md](examples/demo/API.md)

运行示例：

```bash
cd examples/demo

# 运行 Vue 3 版本演示
./run.sh vue

# 或运行 React 版本演示
./run.sh react
```

---

## 本地开发与测试

### Python 后端单元测试

测试基于 `pytest`，需要连接一个可用的 PostgreSQL 测试数据库：

```bash
# 设置测试数据库连接串
export ACCOUNT_KIT_TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/account_kit_test"

# 安装开发依赖并运行测试
pip install -e ".[dev]"
pytest -q
```

### 前端组件包构建与测试

```bash
cd packages/account-ui-vue
npm ci
npm run build
npm run typecheck

# React 包同理
cd ../account-ui-react
npm ci
npm run build
npm run typecheck
```

### 版本发布流程

1. 确认版本号一致：`pyproject.toml`、`src/account_kit/__init__.py` 的 `__version__` 以及两个 `packages/*/package.json` 的 `version` 必须保持相同。
2. 推送版本 Tag（如 `v0.2.2`）：
   ```bash
   git tag v0.2.2
   git push origin v0.2.2
   ```
3. GitHub Actions 自动执行：
   - 检查三处版本号与 Tag 一致性并执行完整自动化测试。
   - 通过 **PyPI Trusted Publishing**（OIDC 免密认证）将 Python 包发布到 PyPI。
   - 使用 `GITHUB_TOKEN` 将前端组件包发布到 **GitHub Packages**。

---

## 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。
