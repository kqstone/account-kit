# 版本升级说明 (Upgrade Guide)

本文档整理了 `account-kit` 版本迭代过程中的架构变更、破坏性改动 (Breaking Changes) 及平滑迁移指南。

---

## 升级至 0.2.3（单一管理员与后台安全）

应用层改动随包升级即生效，**不必改宿主代码**即可获得：

- 管理员登录默认 5 次失败锁定 15 分钟（`admin_login_lockout_attempts=5`）
- `PATCH` / `DELETE` 不能再改 `is_admin`、不能删停管理员
- 登录审计 meta 含 `is_admin`
- 管理员 `POST /2fa/setup` 默认必须带当前密码
- 后台路由不再接受 `?token=`
- 撤审批后 access token 立刻失效

原先靠 `PATCH {admin}/users/{id}` 提权或贬谪管理员的脚本会收到 400 `ADMIN_FLAG_IMMUTABLE`。改为宿主侧 `ensure_admin` 或直接写库（仅用于引导）。

### 数据库

新增部分唯一索引：至多一行 `auth.users.is_admin = true`。

**用 Python（推荐，每次启动可跑）：**

```python
from account_kit import ensure_schema

await ensure_schema(engine)
```

`ensure_schema` / `init_db` / `ensure_schema_sync` 都会尝试创建 `uq_users_single_admin`。

**用手写 SQL（无 Alembic 的宿主）：** 在已执行 `upgrade_0_2_2.sql` 的库上再跑包内

`account_kit/sql/upgrade_0_2_3.sql`

（`account_kit.schema_setup.upgrade_sql("0.2.3")` 可读到同一份。）

### 库里已经有多名管理员

**不会破坏性失败。** `ensure_schema` 和 upgrade SQL 发现 `count(*) WHERE is_admin = true > 1` 时跳过建索引，并打 warning（Python logger `account_kit.schema`，SQL 为 `RAISE WARNING`）。

处理步骤：

```sql
SELECT id, username, email, is_active
FROM auth.users
WHERE is_admin = true;
```

只保留一名管理员，其余改为普通用户：

```sql
UPDATE auth.users
SET is_admin = false
WHERE id <> '<留下的管理员 UUID>';
```

然后建索引：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_admin
  ON auth.users (is_admin) WHERE is_admin = true;
```

或再跑一次 `ensure_schema` / `upgrade_0_2_3.sql`。

索引未建期间，应用层 API 仍然拒绝第二名管理员，但并发直写库可能插入第二行，请尽快收束。

### 行为变化清单

| 变化 | 兼容性 |
|---|---|
| `PATCH` 带 `is_admin` 400 | 破坏：宿主提权脚本需改为 `ensure_admin` / 写库 |
| 删除/停用管理员 400 | 破坏：清库脚本需跳过管理员 |
| 管理员 lockout 默认开 | 管理员连错 5 次会 429，普通用户默认不受影响 |
| `?token=` 后台 401 | 头像 GET 仍可用 query token |
| 撤审批后 `/me` 403 | 原先 access 仍可用直到过期 |
| `ensure_admin` 拒绝接管同名非管理员 | demo setup 对非空库不再劫持账号 |

---

## 升级至 0.2.2

### 1. 数据库结构升级 (必做)

0.2.2 版本新增了 4 张核心数据表，用于安全状态持久化与新特性支持，**已有数据表的列与约束完全未做更改**：
- `auth.rate_limit_counters`（分布式频控限流与登录失败计数）
- `auth.two_factor_challenges`（跨实例两步验证登录挑战）
- `auth.refresh_tokens`（刷新令牌家族与轮换记录）
- `auth.captcha_challenges`（内置图形验证码挑战）

#### 迁移执行方式：
- **无迁移框架宿主（推荐）**：在宿主应用启动事件（Lifespan）中调用 `await ensure_schema(engine)`（同步引擎可用 `ensure_schema_sync(engine)`）。该方法内部幂等执行 `CREATE SCHEMA IF NOT EXISTS auth` 及表结构补齐，可安全在每次服务启动时运行。
- **全新数据库**：直接调用 `await init_db(engine)` 或 SQLAlchemy 原生 `Base.metadata.create_all` 均会自动创建全部表结构。
- **使用 Alembic 的宿主**：执行或合并随包附带的 SQL 脚本：
  ```python
  from account_kit.schema_setup import upgrade_sql
  sql_script = upgrade_sql("0.2.2")  # 读取包内 sql/upgrade_0_2_2.sql 内容
  ```

---

### 2. `PATCH /me` 修改邮箱行为变动

在 0.2.1 及更早版本中，用户资料修改端点允许直接提交 `email` 字段进行更新。在 0.2.2 中：
- `profile_email_change` 默认值变更为 `"verify"`：若请求体包含 `email`，必须同时传入 `email_code`（通过 `/me/email/send-code` 预先发至新邮箱）以及当前密码 `current_password`，否则服务端直接返回 `400 EMAIL_VERIFICATION_REQUIRED`。
- **前端适配**：建议接入界面包的 `ChangeEmailForm` 组件或引导至独立换绑端点 `POST /me/email`。
- **兼容过渡方案**：若宿主旧版前端尚未适配验证码流程，可在 `AccountKitConfig` 中显式设置：
  ```python
  AccountKitConfig(..., profile_email_change="direct")
  ```
  设置为 `"direct"` 可暂时恢复为旧版不校验邮箱验证码的行为（不推荐长期使用）。

---

### 3. 短期安全状态存储后端变更

- **默认行为**：`state_backend="db"`。登录失败计数、各端点限流计数、2FA 挑战及图形验证码统一持久化在 PostgreSQL 数据库中，实现跨多工作进程、跨容器集群的状态共享，服务重启不丢失。
- **切回内存**：若项目为单进程且不希望产生数据库频控读写，可显式配置 `state_backend="memory"` 恢复为 0.2.1 的进程内内存存储。
- **单元测试注意**：在 `state_backend="db"` 模式下，旧代码调用 `login_fail_tracker.clear_all()` 不再会清空数据库中的计数表。测试环境建议在配置中指定 `state_backend="memory"`，或在测试夹具中主动清空 `auth.rate_limit_counters` 表。

---

### 4. 账号库内置注册 `/logout` 端点

- 0.2.2 在 `mount_account` 中默认自动挂载了注销端点（`logout_enabled=True`，路径默认为 `{api_prefix}/logout`）。
- 该端点支持无 Body、JSON 或 Form 提交，宽容处理过期 Token，并能自动吊销关联的会话及 Refresh Token。
- **注意**：如果宿主应用此前在 `mount_account` 之后自行定义了相同路径的注销路由，宿主路由可能会被覆盖。如需完全保留宿主自建路由，可在配置中设 `logout_enabled=False` 或修改 `logout_path`。

---

### 5. 内部底层 API 变更为异步 (async)

为了配合数据库存储后端，以下内部服务层函数调整为异步并要求传入 `db: AsyncSession`：
- `mfa_required(db, ...)`
- `captcha.*` 下的校验与清理逻辑
- 2FA 挑战管理：`create_challenge(db, ...)`、`load_challenge(db, ...)`、`save_challenge(db, ...)`、`discard_challenge(db, ...)`
- 旧版同步的 `challenge_store` 仍然保留可导入，调用不会报错但不再具有实际持久化效力。

---

### 6. 新增安全功能一览

- **验证码防爆破与限流**：单邮箱单用途输错达到 `verify_code_max_attempts`（默认 5 次）将自动作废并锁定；全站验证码发信 IP/邮箱频控上线。
- **刷新令牌 (Refresh Token)**：支持可选开启 `refresh_token_enabled=True`，具备轮换机制与令牌重用安全下线防御。
- **账号自助注销**：支持可选开启 `self_delete_enabled=True`，并提供物理删除 (`"hard"`) 与数据脱敏软删除 (`"soft"`) 两种模式。
- **安全审计日志**：自动记录密码修改、登录失败、2FA 变更、权限修改等敏感事件至 `auth.auth_audit_logs` 表，支持后台分页查询。
- **内置图形验证码**：支持通过 `captcha_builtin=True` 开箱即用生成图片验证码。

---

## 升级至 0.2.0

### 1. 邮件模板覆盖机制
- **内置模板体系**：两步验证相关邮件（`login_2fa` / `disable_2fa`）默认使用 `two_factor_login_{zh,en}.html` 和 `two_factor_disable_{zh,en}.html`；其他用途默认使用 `verification_{lang}.html`。
- **宿主自定义覆盖**：
  - 配置 `email_template_dir`：Jinja2 模板引擎将优先从该目录加载同名模板文件，找不到时自动回退到包内默认模板。
  - 配置 `email_template_map`：可将指定 `purpose` 映射至宿主指定的相对路径模板文件（支持 `{lang}` 语言占位符）。

### 2. 独立修改密码端点
- 新增 `POST {api_prefix}/change-password` 端点，请求体为 `{ "old_password", "new_password" }`。
- 默认直接通过校验旧密码完成修改，无需邮箱验证码；若宿主需要更严格的安全控制，可配置 `change_password_require_email_code=True` 强制要求附带验证码。
- 修改成功后会自动吊销全部受信任设备并销毁未完成的 2FA 挑战；在单设备模式下将清空会话。

### 3. 可选用户头像系统
- 新增用户头像支持（默认关闭，配置 `avatar_enabled=True` 开启）。
- 由宿主应用注入 `avatar_save`、`avatar_delete`、`avatar_open` 存储回调，kit 自身不强制依赖图像处理库（Pillow）。
- 提供端点：`POST /me/avatar`、`DELETE /me/avatar`、`GET /users/{id}/avatar`。

### 4. 角色变更申请查询
- 新增 `GET {api_prefix}/role-change-requests/me` 端点，允许当前登录用户查询自身待审核的角色变更申请。
