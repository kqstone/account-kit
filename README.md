# account-kit

dedd-online 与 dental-case-pro 共用的异步账号包。PostgreSQL + SQLAlchemy + asyncpg，表在 `auth` schema，用户主键是 UUID。

账号能力：注册、登录、邮件验证码、审批、单设备会话、自定义角色、后台权限（`is_admin`，不是角色）、等级目录、两步验证。限额、限流、积分留在宿主。

```python
from account_kit import init_db, mount_account, seed_defaults
from account_kit.config import AccountKitConfig

await init_db(engine)
await seed_defaults(session)
mount_account(app, get_db, AccountKitConfig(jwt_secret="..."))
```

打 tag `v*` 时 GitHub Action 把 Python wheel 挂到 GitHub Release，并把下面两个包发到 GitHub Packages。GitHub Packages 没有 PyPI 注册表。不单独发布 client 包，请求客户端打进这两个界面包。

- `@kqstone/account-ui-vue`：`LoginForm`、`RegisterForm`、`ResetPasswordForm`、`TierBadge`
- `@kqstone/account-ui-react`：同上

宿主页面替换留到各自仓库的下一步。安装前在 `.npmrc` 写 `@kqstone:registry=https://npm.pkg.github.com`。
