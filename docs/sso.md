# OIDC Identity Provider (0.5.0)

account-kit 可作为 **Authorization Code + PKCE S256** 的可选 IdP。账号仍是本站 kit 会话（Bearer）；授权码与 `id_token` / SSO `access_token` **独立于登录 JWT**（独立密钥与算法，不回落 `jwt_secret`）。

模块默认关闭。`sso_idp_enabled=False` 时不注册路由（404）。挂载后热关 → 403 `SSO_DISABLED`。热开必须重新 `mount_account`。

`sso_links` 不进 kit（宿主表）。RP 用换码结果按 email 关联本地用户后，调用已有的 `complete_login_tokens` 发**本站** token。

详细配置见 [configuration.md](configuration.md)；HTTP 契约摘要见 [api.md](api.md)；升级见 [upgrade.md](upgrade.md)。

---

## 打开模块

```python
import os
from account_kit.config import AccountKitConfig, SsoClientConfig

config = AccountKitConfig(
    jwt_secret=os.environ["JWT_SECRET"],
    sso_idp_enabled=True,
    sso_issuer="https://gingiva.top:8443",  # 去尾斜杠；生产必须 https
    sso_jwt_algorithm="RS256",
    sso_signing_key_pem=os.environ["SSO_SIGNING_KEY_PEM"],
    sso_clients=(
        SsoClientConfig.from_env("ACCOUNT_KIT_SSO_CLIENT_DEDD", name="DEDD"),
        SsoClientConfig.from_env("ACCOUNT_KIT_SSO_CLIENT_DENTAL", name="Dental"),
    ),
)
```

`from_env("ACCOUNT_KIT_SSO_CLIENT_DEDD")` 读取 `ACCOUNT_KIT_SSO_CLIENT_DEDD_SECRET`（以及可选 `_ID` / `_REDIRECT` / `_NAME`）。密钥不要进任何 GET 配置接口或前端。

未配 issuer / 签名材料 / 客户端 → 发现文档与业务路由 503 `SSO_NOT_CONFIGURED`。测试可用 `sso_allow_http_issuer=True`。

`ensure_schema` / `init_db` / `upgrade_sql("0.5.0")` 会创建 `auth.oauth_authorization_codes`。关模块的宿主可不建此表。

---

## 签名

- **默认 RS256**：`sso_signing_key_pem` 为 RSA 私钥；`/.well-known/jwks.json` 公布公钥和 `kid`。
- **可选 HS256**：`sso_jwt_algorithm="HS256"` 时用**该 client 的 client_secret** 签 `id_token` 与 SSO `access_token`。JWKS 为空。
- 两种都不回落 `jwt_secret`。登录 JWT 不能当 userinfo Bearer。

---

## 路由

授权页是宿主 SPA：用户登录 kit 后点确认，**POST** 发码（无 Cookie GET authorize，无 kit 提供的 HTML）。

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| GET | `/.well-known/openid-configuration` | 发现文档。`sso_mount_well_known_root=False` 则不挂根路径 |
| GET | `/.well-known/jwks.json` | RS256 公钥；HS256 为 `{"keys":[]}` |
| GET | `{api_prefix}/.well-known/openid-configuration` | 同上，备用 |
| POST | `{api_prefix}/oauth/authorize` | 已登录 kit Bearer。JSON 签发 code |
| POST | `{api_prefix}/oauth/token` | 仅 form；`client_secret_post` 或 `basic`（不可同时） |
| GET | `{api_prefix}/oauth/userinfo` | Bearer = SSO access_token |

authorize 校验顺序：`client_id` → `redirect_uri` **精确字符串**白名单（不规范化、不回跳）→ `response_type=code` → `scope` 含 `openid` → **必填** `state`（原样回传）→ PKCE S256（challenge 长度 43–128）。nonce 可选，最长 256，写入 `id_token`。

200：`{code, state, redirect_uri, expires_in}`。取消由宿主 302 `redirect_uri?error=access_denied&state=`。

token：`Cache-Control: no-store`、`Pragma: no-cache`。先认证 client（不存在时仍对哑值做常量时间比较），再 `SELECT FOR UPDATE` 授权码并在同一事务写 `consumed_at`。PKCE 失败也会作废该 code。重放 → `SSO_CODE_INVALID`，并把已签出 access_token 的 `jti` 作废。`redirect_uri` 必填且与存值逐字节相同。不发 refresh_token。

---

## 令牌声明

`id_token`：`iss`（去尾斜杠）、`sub=users.id`、`aud=client_id`、`nonce`、`email`、`email_verified`、`name`、`preferred_username`、`username`、`iat`/`exp`（默认 300s）。

SSO `access_token`：同一套算法；`aud=<issuer>/userinfo`、`jti`、`token_use=access`，以及同样的 profile 声明。userinfo 响应含 `sub` + 上述 profile 字段。

**拒绝 SSO**：管理员 `SSO_ADMIN_FORBIDDEN`；无有效邮箱（空、无 `@`、`@deleted.invalid`）`SSO_EMAIL_REQUIRED`；停用/未审批沿用 `USER_DISABLED` / `ACCOUNT_PENDING`。authorize 与 token 都查。不调 `complete_login_tokens`。

改密 / 重置 / 删用户在 `sso_idp_enabled=True` 时作废未消费 code。

---

## RP 辅助

```python
from account_kit.sso import (
    discover,
    exchange_authorization_code,
    fetch_userinfo,
    verify_id_token,
    MemoryDiscoveryCache,
)

doc = await discover("https://gingiva.top:8443", cache=MemoryDiscoveryCache(), ttl=3600)
# cache=False 跳过缓存；None 用进程内默认缓存
tokens = await exchange_authorization_code(
    issuer="https://gingiva.top:8443",
    client_id="dedd",
    client_secret=secret,
    code=code,
    redirect_uri=redirect,
    code_verifier=verifier,
)
claims = verify_id_token(
    tokens["id_token"],
    issuer="https://gingiva.top:8443",
    audience="dedd",
    nonce=nonce,
    jwks=jwks,              # RS256
    client_secret=secret,   # HS256
)
profile = await fetch_userinfo(issuer="https://gingiva.top:8443", access_token=tokens["access_token"])
```

`verify_id_token` 校验 **iss / aud / exp / nonce / 签名**（JWKS 或 HS256 secret）。

宿主 finish：用 `iss`/`sub` 查自己的 `sso_links`。命中则 `assert_login_allowed` 后发本站 token。未命中但 email 唯一命中且 `sso_email_auto_link=True` 且 `email_verified=true` 则自动写 link。**未知身份禁止 `create_user`**，签发 `bind_ticket` 返回 `bind_required`。管理员账号不要走 SSO。

---

## RP 绑定已有用户（0.7.0）

kit 提供票与校验，**不**注册 `/sso/bind-existing` 等 RP 路由。`sso_links` 仍在宿主。

| helper | 职责 |
|---|---|
| `issue_bind_ticket` / `load_bind_ticket` / `consume_bind_ticket` | 600s 一次票。消费 `SELECT FOR UPDATE` + `populate_existing` |
| `verify_bind_target` | 密码 + captcha + lockout + 审批 + 可选禁管理员 + 2FA。可选 `challenge_token` + 已加载的 `bind_ticket` 行 |
| `attach_mfa_challenge` / `discard_bind_mfa_challenge` / `discard_challenge` | 把登录 2FA 挑战绑到票上；绑定+发 token **全部成功后**才 discard |
| `provision_user(source="sso", password_set=False, commit=False)` | 仅 create-account。读当前 `require_approval`。`commit=False` 不发邮件 |
| `notify_admins_pending` / `notify_user_approval_decision` | 宿主自己 commit 成功后再显式发信 |

### 宿主 `POST /sso/bind-existing`

Body：

```
bind_ticket, username, password,
force?, device_name?,
code?, recovery_code?, email_code?,
captcha_id?, captcha_code?,
reclaim?,
challenge_token?
```

前端 `SsoBindExistingPayload.challengeToken` 对应 `challenge_token`。微信 bind-existing 不传此字段，仍走 kit `POST /login/2fa`。

校验顺序：密码 / captcha / lockout / `assert_login_allowed` / 禁管理员始终执行。2FA：

1. 未带第二因素 → `401 MFA_REQUIRED`（`challenge_token` + 原样 `bind_ticket`）。**票不消费**。宿主 `attach_mfa_challenge(ticket, challenge_token)`，关联写在 **票行** `mfa_challenge_hash` 上（不信任客户端自报 jti）。
2. 带码 + `challenge_token` + 宿主传入已加载的 `bind_ticket` 行 → 校验挑战未过期、`user_id` 为当前用户、票 hash 与用途一致，然后 `verify_second_factor`，置 `item.passed=True`，**helper 内不 discard**。
3. 同一用户同一票再次 POST（force / reclaim），码可空：已 `passed` 的挑战直接过 2FA，不重用已消费的 TOTP/恢复码/邮箱码。
4. 跨用户 / 跨票 / 不同用途 / 过期 → `MFA_CHALLENGE_INVALID`。
5. 写 `sso_links` + `consume_bind_ticket(commit=False)` + `complete_login_tokens` **全部成功** 后：`discard_bind_mfa_challenge`（或 `discard_challenge` + 清空 `ticket.mfa_challenge_hash`）。409 `ALREADY_LOGGED_IN` / `SSO_ORPHAN_PENDING` **不要** discard，把错误回给前端；前端带同一 `challenge_token` 重试。

不要走 kit `POST /login/2fa` 完成 SSO 绑定（命中 bind_ticket 会 400 `SSO_BIND_TICKET_INVALID`）。邮箱码仍用 `POST /login/2fa/email/send`。

```python
from account_kit import (
    attach_mfa_challenge, consume_bind_ticket, discard_bind_mfa_challenge,
    load_bind_ticket, verify_bind_target,
)
from account_kit.i18n import AccountError, error_code_of

ticket, claims = await load_bind_ticket(db, raw, config=get_config())
try:
    user = await verify_bind_target(
        db, get_config(), request,
        username=..., password=...,
        code=..., recovery_code=..., email_code=...,
        challenge_token=body.challenge_token or "",
        bind_ticket=ticket,
        forbid_admin=True,
        login_purpose="sso_bind",
    )
except AccountError as exc:
    if error_code_of(exc) == "MFA_REQUIRED":
        extra = dict(exc.kit_extra)
        extra["bind_ticket"] = raw
        await attach_mfa_challenge(db, ticket, extra["challenge_token"])
        raise account_error(401, "MFA_REQUIRED", extra=extra)
    raise
# 写 sso_links（含 reclaim）；409 时不要 discard 挑战
await consume_bind_ticket(db, raw, config=get_config(), commit=False)
user, tokens = await complete_login_tokens(db, get_config(), user, force=force, ...)
await db.commit()
await discard_bind_mfa_challenge(db, ticket, body.challenge_token or "")
```

`complete_login_tokens(force=False)` 在 `single_device` 下可能 409 `ALREADY_LOGGED_IN`。此时票仍是 issued、挑战仍是 passed，前端强制登录重试同一 `challenge_token`（空码 + `force=true`）。

`SSO_ORPHAN_PENDING` 同样回传外层：`BindExistingAccountForm` / `TwoFactorLoginDialog` 保留已通过的 `challengeToken`，确认后 `reclaim=true` 再 POST。

- `POST /sso/create-account`：此处才做邮箱域名限制。`sso_allow_create=False` → `SSO_CREATE_DISABLED`。`provision_user(..., commit=False)` 后宿主写 link 并 commit，再 `notify_admins_pending`（pending 时）。`on_pending_user` 仍在事务内运行。
- `POST /sso/bind/start`、`GET /sso/binding`、`POST /sso/unbind`：个人中心。解绑时 `password_set=false` → `SSO_UNBIND_PASSWORD_REQUIRED`。审计 `sso_bound` / `sso_unbound` / `login_sso`。

reclaim：占用方同时 `pending + password_set=false + approved_at is NULL` 时默认 409 `SSO_ORPHAN_PENDING`；`reclaim: true` 改绑到老号，空号保留给管理员删除。

前端：`SsoBindPanel` / `BindExistingAccountForm` / `SsoBindSettings`。kit 不注册 RP 路由。

---

## 错误码

kit 顶层 `code` + 本地化 `detail`；OAuth 顶层 `error` / `error_description`（与文案相同）。`SSO_INVALID_CLIENT` 为 401 并带 `WWW-Authenticate`。

`before_action`：`sso_authorize` `sso_token` `sso_userinfo`。审计：`sso_authorize` `sso_token`（meta 只有 `client_id`，无 secret）。
