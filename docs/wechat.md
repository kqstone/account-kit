# 微信小程序码登录 (0.4.0)

网页 / 桌面 / App 展示微信小程序码；医生用微信扫码，在小程序确认后，**该端**拿到与 `POST /login` 相同形状的 token。小程序只用 `wx.login` 换 openid，**不发 JWT、不保持医生登录态、不占 `users.current_session_id`**。没有伴生会话，不必改宿主 `get_current_user` 的 `sid` 规则。

模块默认关闭。`wechat_enabled=False` 时不注册任何 `/login/wechat/*` 或 `/wechat/*` 路由，其它 0.3.0 行为不变。

详细配置见 [configuration.md](configuration.md)；HTTP 契约摘要见 [api.md](api.md)；升级见 [upgrade.md](upgrade.md)。

---

## 打开模块

```python
import os
from account_kit.config import AccountKitConfig

config = AccountKitConfig(
    jwt_secret=os.environ["JWT_SECRET"],
    wechat_enabled=True,
    wechat_app_id=os.environ["WECHAT_APP_ID"],
    wechat_app_secret=os.environ["WECHAT_APP_SECRET"],  # 只在服务端；不要进任何 GET 配置接口
    wechat_env_version="trial",   # 联调：trial 或 develop；生产：release
    wechat_check_path=False,      # 未发布必须 False；生产 True
)
```

未配 AppID/Secret 且未注入 `wechat_code2session` / `wechat_get_wxacode` 时，`POST /login/wechat/start` 返回 503 `WECHAT_NOT_CONFIGURED`。不要把 AppSecret 写进 demo 或前端。

`ensure_schema` / `init_db` / `upgrade_sql("0.4.0")` 会创建 `auth.wechat_identities` 与 `auth.wechat_login_tickets`。

---

## 配置

全部可选，默认关。`wechat_app_secret` 只在服务端使用。

| 字段 | 默认 | 说明 |
|---|---|---|
| `wechat_enabled` | `False` | 关则不注册路由 |
| `wechat_app_id` | `""` | 小程序 AppID |
| `wechat_app_secret` | `""` | 服务端密钥 |
| `wechat_qr_ttl_seconds` | `120` | ticket 有效期；过期后前端再调 start |
| `wechat_qr_page` | `"pages/login/confirm"` | `getwxacodeunlimit` 的 `page` |
| `wechat_bind_page` | `"pages/login/confirm"` | 设置页绑定码，可用同一页 |
| `wechat_env_version` | `"release"` | `release` / `trial` / `develop` |
| `wechat_check_path` | `True` | 与微信 `check_path` 一致。未发布必须 `False` |
| `wechat_login_rate_limit_ip` | `20` | start / scan / confirm / bind 的 IP 限流（窗口同 `login_rate_window_seconds`） |
| `wechat_satisfies_mfa` | `True` | 已绑定扫码确认视为已过第二因素 |
| `wechat_allow_register` | `True` | 未绑定扫码后允许网页新建账号 |
| `wechat_code2session` | `None` | 测试注入：`js_code -> {openid, unionid?}`，不得回传 `session_key` |
| `wechat_get_wxacode` | `None` | 测试注入：返回 PNG/JPEG bytes |

`before_action` 新增：`wechat_start` `wechat_confirm` `wechat_bind` `wechat_unbind` `wechat_register`。

### 联调与正式发布

官方 [getwxacodeunlimit](https://developers.weixin.qq.com/miniprogram/dev/server/API/qrcode-link/qr-code/api_getunlimitedqrcode.html)：

- `env_version`：`release`（默认）/ `trial` / `develop`。不是「只能生成正式版码」。
- `check_path=true`（默认）时 page 必须已在**正式版**存在，否则微信 41030；`false` 允许未发布。
- 开发版仅开发者可打开；体验版仅体验成员可打开。任意用户必须 `release`。

联调：`wechat_env_version=trial`（或 `develop`）且 `wechat_check_path=False`。生产：`release` + `check_path=True`。

---

## HTTP 契约

前缀 `{api_prefix}`（默认 `/api/auth`）。JSON，不要 form。登录成功的 token 形状 = 现有 `TokenResponse`（`access_token` / `token_type` / 可选 `refresh_token`）。

**没有** `POST /login/wechat`。小程序路径从不返回 `access_token` / `refresh_token` / `session_key`。

### 开码、轮询、刷新

`POST /login/wechat/start` 匿名。body 可选 `{device_name, force}`。限流。调 `getwxacodeunlimit`。失败 502 `WECHAT_QR_FAILED`。200：

```json
{ "ticket": "...", "scene": "...", "expires_in": 120, "image_base64": "...", "mime": "image/png" }
```

过期刷新 = 再调 start（新 ticket、新码）。前端在 `status=expired` 或倒计时到 0 时提供刷新。

`GET /login/wechat/status?ticket=`

| status | 响应 |
|---|---|
| `pending` | `{status, expires_in}` |
| `scanned` | `{status, expires_in, username?}`（打码用户名，不回邮箱） |
| `unbound` | `{status:"unbound", bind_ticket, expires_in}` |
| `confirmed` | **仅第一次**附带 token，随后变为 `consumed` |
| `consumed` / `expired` / `cancelled` / 未知 | 无 token |

`POST /login/wechat/cancel` `{ticket}` 幂等。

网页用 start 返回的 opaque `ticket` 轮询；小程序把 `scene` 放进同一字段 `ticket`（服务端按 ticket 哈希或 scene 查找）。

### 小程序：扫、确认（无登录）

均需 `js_code`。服务端 `code2Session`。禁止回 `session_key`。禁止给小程序 `access_token`。

`POST /login/wechat/scan` `{ticket, js_code, purpose?}`

> 小程序只拿到码里的 `scene`，把它放进 `ticket` 字段即可，服务端按 scene 查票。`purpose` 可选（`login` / `bind`），**以票本身的用途为准**，客户端传的值被忽略。绑定码也可以走 `/login/wechat/scan` + `/login/wechat/confirm`（服务端自动转为绑定，响应 `{status:"ok", purpose:"bind"}`），与 `/wechat/bind/confirm` 等价。scan / confirm 响应都带 `purpose`。

- 未绑定 → `unbound`（小程序只提示回电脑，**不收密码**）
- 已绑定 → `scanned` + `username`（不要回邮箱）

`POST /login/wechat/confirm` `{ticket, js_code, force?}`

- 未绑定 → 401 `WECHAT_NOT_BOUND`
- `is_active` 且已批准；`wechat_satisfies_mfa=True` 时走已过 2FA 的 `complete_login_tokens`
- `single_device` 已在线且未 force → 409 `ALREADY_LOGGED_IN`（detail 与 `/login` 相同），ticket 保持 `scanned`
- 成功：ticket `confirmed`，token 交给 status；小程序 `{status:"ok"}`

### 未绑定：网页绑定已有 / 新建

`POST /login/wechat/bind-existing`

```json
{
  "bind_ticket": "...",
  "username": "...",
  "password": "...",
  "force": false,
  "device_name": "",
  "code": "",
  "recovery_code": "",
  "email_code": ""
}
```

- 验密码，计入现有登录限流 / captcha。
- 开了 2FA 且未带第二因素：返回与 `POST /login` **相同形状**的 401 `MFA_REQUIRED` challenge（`detail` 含 `challenge_token`、`methods`、`email_available`、`expires_in`），并额外带 `bind_ticket`。随后用现有 `POST /login/2fa` 提交 TOTP / 恢复码 / 邮箱码；2FA 成功后 **绑定 openid 并** `complete_login_tokens`。
- 也可在本接口一次带上 `code` / `recovery_code` / `email_code`，跳过独立 2FA 步。
- openid 已被他人 → 409 `WECHAT_ALREADY_BOUND`；本账号已绑其他 openid → 409 `WECHAT_BIND_EXISTS`。
- 成功：写 identity，**本接口直接返回 TokenResponse**，ticket `consumed`（不要再经 status 发第二次）。

`POST /login/wechat/register` `{bind_ticket, username, email, password, code, ...现有注册字段}`

- `wechat_allow_register=False` → 403 `WECHAT_REGISTER_DISABLED`。
- 现有 register 校验。创建用户后写 identity。
- `require_approval`：不发 token，返回现网「待审批」用户形状，ticket `consumed`。
- 否则 `complete_login_tokens`。

### 设置页绑定 / 解绑（已登录）

`GET /wechat/status` → `{bound, openid_masked, bound_at}`。

`POST /wechat/bind/start` → purpose=`bind` 的码；轮询 `GET /login/wechat/status` 直到小程序 confirm。过期同样再 start。绑定码的 status **不**附带 JWT。

`POST /wechat/bind/confirm` `{ticket, js_code}`（小程序）：票上 `user_id` 已在 start 写入；openid 未被占用。小程序仍不拿 JWT。

`POST /wechat/unbind` `{password, code? recovery_code? email_code?}`：密码 +（若开了）第二因素。删 identity，作废开着的票。

---

## 2FA / 单设备 / captcha

| 机制 | 行为 |
|---|---|
| 已绑定扫码 confirm | 不再要 TOTP（`wechat_satisfies_mfa=True`） |
| bind-existing | 必须先过该账号密码；开了 2FA 再过第二因素（challenge 走 `/login/2fa`，或本接口一次带码） |
| 设置页 bind | 调用者已有登录态 |
| captcha | start/scan/confirm 不要求。bind-existing / register 与现网登录/注册相同 |
| 受信设备 | 扫码成功 **默认不**发 |
| 审批 / `is_active` | 与密码登录相同 |
| `single_device` | 发**主会话**。未 force → 409。小程序无会话 |

改密：作废该用户未消费 ticket，**保留**微信绑定。删用户：级联删除 identity。

---

## 数据

`auth.wechat_identities`：`(app_id, openid)` 唯一；`(user_id, app_id)` 唯一。`unionid` 可选，个人主体通常没有，不要当必填。绑定键是 `(app_id, openid)`。

`auth.wechat_login_tickets`：只存 ticket 的 SHA-256 与 scene；scan 后存 `openid_hash`，明文 openid 经 Fernet 放在 `payload_cipher`（confirm 后改为一次性 token 密文，status 读出一次即清空）。`session_key` **不落库**。

`mfa_challenge_hash` 把 bind-existing 发出的 2FA challenge 链到现有 `POST /login/2fa`，不改 `two_factor_challenges` 表。

---

## 错误码与审计

`WECHAT_NOT_CONFIGURED` `WECHAT_QR_FAILED` `WECHAT_CODE_INVALID` `WECHAT_NOT_BOUND` `WECHAT_ALREADY_BOUND` `WECHAT_BIND_EXISTS` `WECHAT_TICKET_INVALID` `WECHAT_TICKET_EXPIRED` `WECHAT_TICKET_CONSUMED` `WECHAT_REGISTER_DISABLED`

复用：`ALREADY_LOGGED_IN` `SESSION_REPLACED` `RATE_LIMITED`、审批/停用/MFA、登录 captcha。

审计：`wechat_bound` `wechat_unbound` `login_wechat` `wechat_register`。没有 `login_wechat_miniapp`。

---

## UI

Vue / React 均导出 `WechatQrLogin`、`WechatBindSettings`。

`WechatQrLogin`：`client`、`deviceName`、`pollMs` 默认 2000、`force`。start → 显示码 → 轮询。过期显示刷新。`@success` / `onSuccess` 与 `LoginForm` 相同。未绑定：组件内置「绑定已有 / 注册」两 tab；开了 2FA 弹出 `TwoFactorLoginDialog`（走 `POST /login/2fa`）。start 503 提示未配置。

`WechatBindSettings`：是否已绑、打码 openid、开绑定码（过期可刷新）、解绑。放 `TwoFactorSettings` 旁。

`createAccountClient`：`startWechatLogin` `wechatLoginStatus` `cancelWechatLogin` `wechatBindExisting` `wechatRegister` `wechatBindStatus` `startWechatBind` `unbindWechat`。

小程序 WXML **不**进 UI 包。

---

## 小程序确认页示例（宿主实现，不进 kit）

`scene` ≤32；`onLoad` 里 `decodeURIComponent(query.scene)`。

```js
// pages/login/confirm.js — 宿主小程序，仅确认页
const API = "https://example.com/api/auth" // 配进 request 合法域名

Page({
  data: { scene: "", status: "loading", username: "", message: "" },
  onLoad(query) {
    const scene = decodeURIComponent(query.scene || "")
    this.setData({ scene })
    this.scan(scene)
  },
  scan(scene) {
    wx.login({
      success: (res) => {
        wx.request({
          url: API + "/login/wechat/scan",
          method: "POST",
          data: { ticket: scene, js_code: res.code },
          success: (r) => {
            const body = r.data || {}
            if (body.status === "unbound") {
              this.setData({ status: "unbound", message: "请回电脑完成绑定或注册" })
            } else if (body.status === "scanned") {
              this.setData({ status: "scanned", username: body.username || "" })
            } else {
              this.setData({ status: "error", message: (body.detail && body.detail.message) || body.detail || "失败" })
            }
          },
        })
      },
    })
  },
  confirm(force) {
    wx.login({
      success: (res) => {
        wx.request({
          url: API + "/login/wechat/confirm",
          method: "POST",
          data: { ticket: this.data.scene, js_code: res.code, force: !!force },
          success: (r) => {
            if (r.statusCode === 409) {
              this.setData({ status: "conflict", message: "该账号已在其他设备登录" })
              return
            }
            if (r.statusCode === 200 && r.data && r.data.status === "ok") {
              this.setData({ status: "ok", message: "请回到电脑或 App" })
              return
            }
            this.setData({ status: "error" })
          },
        })
      },
    })
  },
})
```

设置页绑定码走 `POST /wechat/bind/confirm`，同样把 `scene` 放进 `ticket`，同样不拿 JWT。

---

## 微信服务端 API

- `GET https://api.weixin.qq.com/sns/jscode2session` — [code2Session](https://developers.weixin.qq.com/miniprogram/dev/server/API/user-login/api_code2session.html)
- `GET https://api.weixin.qq.com/cgi-bin/token` 缓存 access_token（提前 5 min 过期）
- `POST https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token=` body：`scene` `page` `env_version` `check_path` `width`

40029 / 40163 → `WECHAT_CODE_INVALID`。使用 `httpx`，超时短，不把微信响应全文给用户。

测试请注入 `wechat_code2session` / `wechat_get_wxacode`，不要打真实微信。
