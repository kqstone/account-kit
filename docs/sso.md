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

宿主 finish：用 `iss`/`sub` 查自己的 `sso_links`，没有则 email 精确匹配后插入，再 `complete_login_tokens`。管理员账号不要走 SSO。

---

## 错误码

kit 顶层 `code` + 本地化 `detail`；OAuth 顶层 `error` / `error_description`（与文案相同）。`SSO_INVALID_CLIENT` 为 401 并带 `WWW-Authenticate`。

`before_action`：`sso_authorize` `sso_token` `sso_userinfo`。审计：`sso_authorize` `sso_token`（meta 只有 `client_id`，无 secret）。
