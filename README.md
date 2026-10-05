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

### 可选：邮箱两步验证、登录图形验证码

两项默认关闭，由宿主在 `AccountKitConfig` 里打开：

- `two_factor_email_enabled=True`：两步验证可用邮箱验证码代替验证器（"跳过 2FA"）。登录时 `POST /login/2fa/email/send`（`challenge_token`、`language`）发码，再把 `email_code` 提交到 `POST /login/2fa`；设置里 `POST /2fa/disable/email-code` 发码，`POST /2fa/disable` 带 `email_code` 关闭。`MFA_REQUIRED` 的 `detail` 里 `email_available` 为真，`methods` 含 `email`。
- `captcha_verifier=fn(captcha_id, captcha_code) -> bool`（可为 async）：同一 IP 或用户名在 `captcha_fail_window_seconds` 内失败 `captcha_fail_threshold` 次后，`POST /login` 必须带 `captcha_id`、`captcha_code`，否则 428 `CAPTCHA_REQUIRED`，错了 400 `CAPTCHA_INVALID`；密码错误返回 401 `INVALID_CREDENTIALS`（带 `captcha_required`）。验证码图片由宿主提供（界面包从 `GET {api_prefix}/captcha` 取 `captcha_id`、`image_base64`）。反向代理后用 `client_ip=fn(request)` 取真实 IP。
- `before_two_factor=async fn(request, user)`：每次校验第二因素、发邮箱码前调用，宿主可在这里限流。
- `two_factor_challenge_ttl_seconds`（默认 300）、`two_factor_max_attempts`（默认 5）：登录两步验证 challenge 的有效期和每个 challenge 允许输错的次数。每次请求时读取，宿主可在 `get_db` 里按后台设置刷新。

`init_db` 和直接调用 `Base.metadata.create_all` 都会先建 `auth` schema（`CREATE SCHEMA IF NOT EXISTS`），空库可直接启动。React 与 Vue 的 `LoginForm` 在服务端要求时都会显示图形验证码。

### 0.2.0：邮件模板覆盖、改密、头像、角色申请查询

- **2FA 邮件模板**：`login_2fa` / `disable_2fa` 默认使用包内 `two_factor_login_{zh,en}.html`、`two_factor_disable_{zh,en}.html`（警示文案，`{{ brand }}` / `{{ code }}`）。其它 purpose 仍用 `verification_{lang}.html`（`{{ action }}` `{{ code }}` `{{ brand }}`）。
- **宿主覆盖模板**：设 `email_template_dir` 后，Jinja 先从该目录按同名加载，找不到再回落包内默认。`email_template_map` 可把 purpose 指到相对文件名（支持 `{lang}`）；拒绝 `..` 与绝对路径。完全接管发送仍可用 `mailer`。
- **`POST {api_prefix}/change-password`**：body `{ "old_password", "new_password" }`，默认**不要求**邮箱验证码（兼容 dedd）。成功后吊销受信设备、丢掉未完成的 2FA challenge；`session_mode==single_device` 时清会话。响应 `{ "status": "success", "detail": "密码修改成功" }`。dental 若要更严，设 `change_password_require_email_code=True`（可再带 `code`）。`PATCH /me` 改密仍走邮箱码，两条路径语义不同。
- **可选头像**（默认关）：`avatar_enabled=True` 并注入 `avatar_save` / `avatar_delete` / `avatar_open`。端点：`POST/DELETE /me/avatar`、`GET /users/{id}/avatar`。存储与图片处理由宿主 callback 完成（Pillow **不是** kit 依赖）。漏配 `avatar_save` 或未启用时返回 501。未提供 `avatar_open` 时，仅当 `avatar_path` 是本地已存在文件才直接读取。
- **`GET {api_prefix}/role-change-requests/me`**：当前用户 pending 申请，没有则 `null`（需 `role_change_enabled`）。

## 安装

Python 包从 [PyPI](https://pypi.org/project/account-kit/) 安装：

```bash
pip install account-kit
```

界面包发在 GitHub Packages（不是 npmjs.com）。安装前在项目根写 `.npmrc`：

```
@kqstone:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NPM_TOKEN}
```

`NPM_TOKEN` 需要带 `read:packages` 的 classic PAT（或等价权限）。CI 里可以用 `GITHUB_TOKEN`，但要先在包的 **Manage Actions access** 里给消费仓库（如 `kqstone/dedd-online`、`kqstone/dental-case-pro`）Read 权限。从 private 仓库首次发布的包默认为 private；可在包设置里改成 public，但无论可见性如何，安装都仍需要 token。

```bash
npm install @kqstone/account-ui-vue    # Vue 3
npm install @kqstone/account-ui-react  # React 18 / 19
```

不单独发布 client 包，请求客户端打进这两个界面包：

- `@kqstone/account-ui-vue` / `@kqstone/account-ui-react`：`LoginForm`、`RegisterForm`、`ResetPasswordForm`、`TwoFactorSettings`、`TwoFactorLoginDialog`、`AvatarUploader`、`UserAvatar`、`ProfileFields`、`TierBadge`、`createAccountClient`

界面包发布的是构建后的 `dist/`（ESM + `.d.ts`），样式在组件首次渲染时注入，不需要单独引入 CSS。2FA 设置页的二维码使用可选 peer `qrcode`，或由宿主传入 `renderQr(otpauthUri) => dataUrl`。文案内置中英，可用 `labels` 覆盖；Vue 不绑 vue-i18n，React 不依赖 antd。

## 本地开发

宿主仓库用 `file:` 路径引用界面包时，先在 account-kit 里构建一次（`npm ci` 会通过 `prepare` 自动构建）：

```bash
cd packages/account-ui-vue && npm ci     # 或 packages/account-ui-react
```

改了界面包源码后，重新 `npm run build`，再在宿主里重新安装依赖。

## 发布

版本号写在 `pyproject.toml`、`src/account_kit/__init__.py` 的 `__version__` 和两个 `packages/*/package.json` 里，发布前三处保持一致。推送 `v<版本号>` tag（如 `v0.2.0`）后，GitHub Action 先校验 tag 与三处版本一致、跑测试和构建，然后：

- Python 包发布到 [PyPI](https://pypi.org/project/account-kit/)（Trusted Publishing，不用 token）
- 两个界面包发布到 [GitHub Packages](https://github.com/kqstone?tab=packages)（`GITHUB_TOKEN`，`packages: write`）

日后若改发 npmjs.com：把 `publishConfig.registry` 改回默认、workflow 改为 `registry.npmjs.org` + `NPM_TOKEN`（或 npm trusted publishing），并更新本节安装说明。

## 许可证

MIT
