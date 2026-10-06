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

### 0.2.2：安全加固、刷新令牌、登出、自助注销、审计日志

**验证码防爆破与发送限流**

- `verify_code_max_attempts`（默认 5）：同一邮箱、同一用途输错达到次数后，该邮箱该用途所有未用验证码作废，返回 400 `验证码错误次数过多，请重新获取验证码`，并记审计 `verification_code_locked`。注册、找回密码、改密、邮箱两步验证、修改邮箱、注销账号都受此限制。
- 发码限流（`send-code`、2FA 邮箱码、修改邮箱、注销账号共用）：`send_code_rate_limit_ip`（10）、`send_code_rate_limit_email`（5），窗口 `send_code_rate_window_seconds`（3600）。名称和默认值沿用 dedd 原来的 `auth_send_code_*`。
- 其它可选限流（0 = 关）：`reset_password_rate_limit_ip`（10）/ `reset_password_rate_window_seconds`（3600）、`register_rate_limit_ip`（0）/ `register_rate_window_seconds`（3600）、`login_rate_limit_ip`（0）、`login_rate_limit_user`（0）、`login_rate_window_seconds`（60）。
- 超限统一返回 429，`detail={"code":"RATE_LIMITED","message":...,"retry_after":秒}`，带 `Retry-After` 头。
- 钩子：`before_send_code=async fn(request, email, purpose)`，每次发验证码邮件前调用；`before_action=async fn(request, action, info)`，在 `send_code`、`verify_code`、`register`、`reset_password`、`change_password`、`change_email`、`refresh`、`logout`、`delete_account`、`captcha` 前调用。抛 `HTTPException` 即拒绝。

**状态存储**：`state_backend="db"`（默认）把登录失败计数、限流计数、2FA 登录 challenge、内置图形验证码放进 `auth` schema 的表，多进程、多实例共享，重启不丢；`state_backend="memory"` 保持 0.2.1 的单进程内存行为。

**修改邮箱需验证**

- `POST /me/email/send-code`，body `{new_email, password?, language}`：把验证码发到新邮箱。新邮箱已被占用时返回 400；同一用户 60 秒内重复发送返回 429 `EMAIL_CODE_TOO_FREQUENT`。
- `POST /me/email`，body `{new_email, code, password?}`：验证码与当前用户绑定，别人的码不能用。`change_email_require_password=True`（默认）时必须带密码。成功后记审计 `email_changed`。
- `PATCH /me` 里的 `email` 由 `profile_email_change` 控制：
  - `verify`（默认）：要带 `email_code`（以及 `current_password`），否则 400 `EMAIL_VERIFICATION_REQUIRED`；
  - `reject`：400 `EMAIL_CHANGE_VIA_ENDPOINT`；
  - `direct`：0.2.1 行为，不验证，不推荐。

**刷新令牌**（`refresh_token_enabled=False`，默认关）

- 打开后，`/login` 和 `/login/2fa` 额外返回 `refresh_token`、`refresh_expires_in`（`refresh_token_expire_days` 默认 30）。关闭时响应字段与 0.2.1 完全一致。
- `POST /refresh` `{refresh_token}`：每次轮换。库里只存 SHA-256 哈希，按 family 组织。错误码：`REFRESH_INVALID`、`REFRESH_EXPIRED`、`SESSION_REPLACED`、`REFRESH_REUSED`。重用旧 token 时吊销整个 family 并清掉 single_device 会话，所以客户端要单飞刷新（界面包已经这样做）。
- 改密、重置密码、关闭或重置 2FA、停用账号、撤销审批、改角色或改 `is_admin`、注销账号都会吊销刷新令牌；single_device 模式下新登录会吊销其它设备的令牌。

**登出**：`POST {api_prefix}{logout_path}`（`logout_enabled=True`，`logout_path="/logout"`）。

- body 可空，也可以是 JSON 或表单 `{refresh_token?, all_devices?}`，总是返回 `{"status":"success"}`。
- access token 过期或会话已被顶替时也返回 200，只在 token 的 `sid` 与当前会话一致时才清会话。吊销该会话的刷新令牌；`all_devices` 吊销全部。
- 记审计 `logout`，回调 `on_logout`。

**自助注销**（`self_delete_enabled=False`，默认关）

- `POST /me/delete`（或 `DELETE /me`），body `{password, code?, recovery_code?, email_code?}`。开了 2FA 的账号必须再给一个因素，否则 400 `MFA_CODE_REQUIRED`；用邮箱码时先调 `POST /me/delete/email-code`。管理员不能自助注销，返回 403 `ADMIN_SELF_DELETE_FORBIDDEN`。
- `user_delete_mode` 同时作用于后台删除和自助注销：
  - `"hard"`（默认）：删行，与 0.2.1 相同；
  - `"soft"`：停用账号，用户名和邮箱改成墓碑值，清空个人资料，吊销所有凭据，清掉 2FA 和头像，保留行以满足外键。
- 两种模式都会先调用 `on_deleted`。

**审计日志**（`audit_log_enabled=True`）

- 写入 `auth.auth_audit_logs`，使用独立事务，业务回滚不影响审计。每写一条回调一次 `on_audit(db, event, user_id, meta)`。
- 事件：`login_success`、`login_failed`、`login_2fa_failed`、`2fa_enabled`、`2fa_disabled`、`2fa_reset`、`2fa_recovery_regenerated`、`password_changed`、`password_reset`、`email_changed`、`logout`、`refresh_reuse_detected`、`account_deleted`、`verification_code_locked`、`admin_user_updated`（含修改前后）、`admin_user_deleted`、`admin_role_changed`、`admin_tier_changed`、`role_change_reviewed`。
- 后台查询：`GET {admin_prefix}/audit-logs?page=&page_size=(≤200)&user_id=&event=a,b&ip=&since=&until=`，返回 `{items,total,page,page_size}`。

**内置图形验证码**（`captcha_builtin=False`，默认关，需要 `pip install "account-kit[captcha]"`）

- 打开后 kit 提供 `GET {api_prefix}/captcha`，返回 `{captcha_id, image_base64, expires_in}`，并自行校验。答案以 HMAC 哈希保存，只能用一次。
- 相关配置：`captcha_ttl_seconds`（300）、`captcha_length`（4）。
- 宿主配置了 `captcha_verifier` 时优先用宿主的。宿主自己的 `/captcha` 路由不受影响，因为未开启时 kit 不注册这个路由。

**数据库变更**：新增 4 张表 `auth.rate_limit_counters`、`auth.two_factor_challenges`、`auth.refresh_tokens`、`auth.captcha_challenges`，已有表的列不变。

- 用 `init_db` 或 `Base.metadata.create_all` 的宿主会自动建表。
- 没有 Alembic 的宿主可以在启动时调用 `ensure_schema(engine)` / `ensure_schema_sync(engine)`，它们会幂等地补建缺失的表。
- 用 Alembic 的宿主执行或照抄 `src/account_kit/sql/upgrade_0_2_2.sql`（随包安装，可用 `account_kit.schema_setup.upgrade_sql("0.2.2")` 读出）。

**从 0.2.1 升级注意**

- `PATCH /me` 直接改邮箱会被拒（默认 `verify`）。前端要改用 `ChangeEmailForm` 或 `/me/email` 流程；过渡期可以设 `profile_email_change="direct"`。dental 资料页目前在 PATCH 里带 `email`，没有验证码，不改的话整次保存都会 400。
- 默认 `state_backend="db"` 后，`login_fail_tracker.clear_all()` 不再清计数。测试里改用 `state_backend="memory"`，或清空 `auth.rate_limit_counters`。
- kit 现在自己注册 `/logout`。宿主在 kit 之后挂同路径的路由会被 kit 的遮住；kit 的行为是 dedd 原逻辑的超集。不想要的话设 `logout_enabled=False`，或改 `logout_path`。
- 下面这些 API 改成了 async，并带 `db` 参数：`mfa_required(db, ...)`、`captcha.*`，以及 2FA challenge 的 `create_challenge` / `load_challenge` / `save_challenge` / `discard_challenge`。`challenge_store` 仍可导入，调用它不会出错，但不再起作用。`admin_reset(db, user_id)` 签名不变。
- 中英混杂的个别错误文案（如 `Incorrect username or password`）没有改，因为客户端和登录失败计数靠它们匹配。

## 安装

Python 包从 [PyPI](https://pypi.org/project/account-kit/) 安装：

```bash
pip install account-kit
pip install "account-kit[captcha]"   # 需要内置图形验证码时（Pillow）
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

- `@kqstone/account-ui-vue` / `@kqstone/account-ui-react`：`LoginForm`、`RegisterForm`、`ResetPasswordForm`、`TwoFactorSettings`、`TwoFactorLoginDialog`、`AvatarUploader`、`UserAvatar`、`ProfileFields`（`passwordEmailCode` 支持改密邮箱验证码）、`ChangeEmailForm`、`DeleteAccountForm`、`LogoutButton`、`CaptchaImage`、`TierBadge`、`createAccountClient`、`createTokenStore`
- `createAccountClient(base, { getToken, logoutPath, autoRefresh: { getRefreshToken, onTokens, onRefreshFailed } })`：登录后收到 401 时单飞刷新一次再重试（需服务端 `refresh_token_enabled`）；新增 `refresh`、`logout`、`sendChangeEmailCode`、`changeEmail`、`deleteAccount`、`sendDeleteAccountEmailCode`；`AccountApiError.code` 取 `detail.code`

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
