# 升级

## 0.2.2 → 0.2.3（单一管理员索引与后台安全）

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
