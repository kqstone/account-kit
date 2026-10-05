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

## 安装

```bash
pip install account-kit
npm install @kqstone/account-ui-vue    # Vue 3
npm install @kqstone/account-ui-react  # React 18 / 19
```

不单独发布 client 包，请求客户端打进这两个界面包：

- `@kqstone/account-ui-vue`：`LoginForm`、`RegisterForm`、`ResetPasswordForm`、`TierBadge`、`createAccountClient`
- `@kqstone/account-ui-react`：同上

界面包发布的是构建后的 `dist/`（ESM + `.d.ts`），样式在组件首次渲染时注入，不需要单独引入 CSS。

## 本地开发

宿主仓库用 `file:` 路径引用界面包时，先在 account-kit 里构建一次（`npm ci` 会通过 `prepare` 自动构建）：

```bash
cd packages/account-ui-vue && npm ci     # 或 packages/account-ui-react
```

改了界面包源码后，重新 `npm run build`，再在宿主里重新安装依赖。

## 发布

版本号写在 `pyproject.toml` 和两个 `packages/*/package.json` 里，三处保持一致。推送 `v<版本号>` tag（如 `v0.1.0`）后，GitHub Action 先校验 tag 与三处版本一致、跑测试和构建，然后：

- Python 包发布到 [PyPI](https://pypi.org/project/account-kit/)（Trusted Publishing，不用 token）
- 两个界面包以 public 发布到 [npmjs.com](https://www.npmjs.com/)

## 许可证

MIT
