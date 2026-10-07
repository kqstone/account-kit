# account-kit 演示应用 (Demo)

本目录为 **account-kit 0.2.2** 的全功能官方演示程序。演示了包括账号注册、验证码流转、密码认证、图形验证码防爆破、TOTP 两步验证 (2FA)、令牌无感刷新、多设备登出、账号自主注销、管理员审批与安全审计日志等全部核心能力。

项目提供 **Vue 3** (`web-vue`) 与 **React 18** (`web-react`) 两套开箱即用的前端实现，共用同一个轻量级 **FastAPI** 后端 (`server/`)。**无需安装或依赖 Docker**，直接连接本地已有 PostgreSQL 即可一键跑通。完整接口契约请参阅 [API.md](API.md)。

---

## 前置条件

- **Python**：3.10+
- **Node.js**：18+（含 npm）
- **PostgreSQL**：一个可连接的可用数据库实例（示例：`127.0.0.1:5432`，用户 `postgres`，库 `akdemo`）
  > **注意**：account-kit 核心依赖 PostgreSQL 的原生特性（如 `asyncpg` 异步驱动、Schema 隔离、`INSERT ... ON CONFLICT` 原子 Upsert 等），**不支持 SQLite**。

---

## 一键启动

### 1. 运行预构建版本 (推荐)

脚本将自动创建虚拟环境 `.venv`、安装 Python 依赖（含 `account-kit[captcha]` 与 `uvicorn`）、构建本地 UI 组件包与选定前端，并在 `8000` 端口启动服务：

```bash
cd examples/demo

# 启动 Vue 3 版本前端
./run.sh vue
# 或通过 Makefile
make run WEB=vue

# 启动 React 版本前端
./run.sh react
# 或通过 Makefile
make run WEB=react
```

服务就绪后，在浏览器中打开：**<http://127.0.0.1:8000>**。

### 2. 开发模式 (前后端热重载)

如需对后端或前端代码进行二次开发，可开启开发模式：

```bash
# 终端 1：以热重载模式启动 FastAPI 后端服务 (:8000)
./run.sh vue --dev
# 或
make dev WEB=vue

# 终端 2：启动 Vite 前端开发服务器 (:5173，自动将 /api 代理至 :8000)
cd web-vue        # 或 cd web-react
npm install
npm run dev
```

在浏览器中打开 Vite 开发地址：**<http://127.0.0.1:5173>**。

---

## 初始化向导 (Setup Wizard)

首次打开应用时，系统检测到尚未配置数据库（`/api/setup/status` 返回 `initialized: false`），全站路由将强制重定向至 `/setup` 初始化向导页面。

向导涵盖以下配置：
1. **PostgreSQL 连接**：输入主机、端口、用户名、密码与数据库名称，支持点击「测试连接」（调用 `POST /api/setup/test-db`）确认数据库连通性。
2. **超级管理员账号**：设置首个管理员的用户名、邮箱及登录密码（密码长度 ≥ 6 位）。
3. **功能特性开关**：按需启用/禁用 Refresh Token、图形验证码、自主注销、2FA（含邮箱 2FA 途径）、用户注册审批 (`require_approval`)、登出管理、审计日志与角色申请。
4. **邮件服务模式**：
   - `console`（默认）：控制台打印邮件内容，同时记录至内存信箱（可通过 `/api/demo/outbox` 查询），本地无需配置 SMTP。
   - `smtp`：配置真实 SMTP 发信服务（如 MailHog 或第三方企业邮箱）。

向导提交（`POST /api/setup/init`）后：
- 自动执行 `init_db` 创建 `auth` Schema 与数据表，并执行 `seed_defaults` 注入初始角色与等级。
- 配置保存至 `server/.demo-config.json`（已被 `.gitignore` 忽略，且**不持久化管理员密码**）。
- 服务在**同一进程内即时挂载** account-kit 子应用，**无需重启进程**。
- 初始化完成后，`/api/setup/init` 与 `/api/setup/test-db` 接口自动锁定，再次请求将返回 `409 ALREADY_INITIALIZED`。

> **重置方法**：如需重新体验向导或重置环境，只需删除 `examples/demo/server/.demo-config.json` 并重启服务即可。

---

## 分步使用指南

以下以 Vue 版本界面为例，展示 account-kit 的完整功能流转：

### 1. 初始化向导配置
启动后访问首页，首先进入数据库与管理员初始化页面：

![初始化向导](docs/screenshots/vue-setup.png)

配置数据库连接并通过「测试连接」校验，设定管理员账号与功能开关后点击「完成初始化并启动系统」。

### 2. 用户注册与站内信箱取码
初始化完成后跳转至登录/注册界面。点击「注册新账号」：

![用户注册](docs/screenshots/vue-register.png)

输入用户名、邮箱与密码，点击「获取验证码」。在控制台模式下，打开右侧抽屉或点击导航栏的「📬 站内信箱」即可实时获取发送给该邮箱的 6 位验证码：

![站内信箱](docs/screenshots/vue-outbox.png)

复制验证码填入注册表单提交即可完成注册（若开启了用户审批，状态将设为待审批）。

### 3. 用户登录与会话建立
使用刚才注册的用户或初始管理员账号进行登录：

![用户登录](docs/screenshots/vue-login.png)

登录成功后，前端将 Access Token 与 Refresh Token 安全存储至 `account-kit:tokens` 存储桶中，并跳转至账号管理主页。

### 4. 图形验证码防爆破
当连续输入错误密码达到阈值（默认为 3 次）时，后端将返回 `428 CAPTCHA_REQUIRED` 状态码，前端登录框将自动唤起基于 Pillow 动态生成的点阵验证码：

![图形验证码](docs/screenshots/vue-captcha.png)

必须正确填写图形验证码与密码方可继续尝试，有效防止撞库与暴力破解攻击。

### 5. 账号中心：资料修改、修改密码与修改邮箱
登录进入 `/account` 个人中心，可查看个人等级徽章（`TierBadge`）、审批状态及所属角色：

![账号管理](docs/screenshots/vue-account.png)

- **基本资料**：更新姓名、性别、所属机构等信息。
- **修改密码**：输入原密码与新密码完成更新。
- **修改邮箱**：输入新邮箱并点击发送验证码（`purpose="change_email"`），从站内信箱获取验证码并输入当前密码确认，完成平滑换绑。

### 6. 两步验证 (2FA / MFA)
在账号中心的「两步验证」标签页中开启 2FA：

![两步验证](docs/screenshots/vue-2fa.png)

- **TOTP 密钥绑定**：使用认证器 App（Google Authenticator、1Password 等）扫描二维码并校验动态口令。
- **紧急恢复码 (Recovery Codes)**：绑定成功后一次性生成备用恢复码，妥善保管以防设备丢失。
- **2FA 登录挑战**：开启 2FA 的账号再次登录时，密码校验通过后将触发 `401 MFA_REQUIRED`，唤起第二因素校验弹窗；支持选择 TOTP 口令、备用恢复码或邮箱验证码进行认证。
- **受信任设备**：支持勾选「在此设备上保持 30 天信任」，后续登录可自动跳过第二因素。

### 7. 登出与全部设备登出
在个人主页右上角提供双模式退出操作：
- **普通登出**：吊销当前会话并清除本地凭证。
- **全部设备登出**（`allDevices: true`）：调用后端一次性吊销该用户在所有设备上发放的所有 Refresh Token，全域会话立即失效。

### 8. 刷新令牌 (Refresh Token) 机制
系统内置 Access Token 与 Refresh Token 双令牌机制：
- 前端 API 客户端配置了 `autoRefresh`，在 Access Token 即将过期时自动发起 `POST /api/auth/refresh` 无感换发新令牌。
- Refresh Token 采用严格的单次轮换（Rotation）策略。一旦检测到旧 Refresh Token 被重复使用，系统将判定存在重放攻击风险，返回 `401 REFRESH_REUSED` 并立即吊销该家族全部令牌。

### 9. 自助注销账号
在账号中心「危险操作」标签页中：
- 普通用户输入当前登录密码（若开启 2FA 还需校验 TOTP 或邮箱验证码）即可执行彻底注销（Hard Delete）。
- 超级管理员账号受底层安全保护，禁止自助注销（接口返回 `400 ADMIN_SELF_DELETE_FORBIDDEN`）。

### 10. 后台管理：用户审批与安全审计日志
以管理员账号登录后，顶部导航栏将出现「后台管理」入口：

- **用户列表与审批管理**：
  查看全系统注册用户，直接处理待审批账号（通过 / 拒绝）、启停账号、授权或撤销管理员、重置用户 2FA 绑定以及删除用户。
  ![后台用户管理](docs/screenshots/vue-admin.png)

- **全局安全审计日志**：
  检索全站安全事件（包含登录成功、登录失败、2FA 状态变更、修改密码、修改邮箱、令牌重用预警、账号注销、管理员权限变更等），支持按事件类型、用户 ID 及客户端 IP 进行多条件过滤检索。
  ![审计日志](docs/screenshots/vue-audit.png)

---

## React 版关键页截图对照

React 版（`web-react`）基于 `@kqstone/account-ui-react` 实现，与 Vue 版共用完全一致的后端逻辑契约与视觉设计系统。以下为各关键页面的对照：

| 功能模块 | Vue 3 版本 (`web-vue`) | React 18 版本 (`web-react`) |
|:---|:---|:---|
| **初始化向导** | ![Vue Setup](docs/screenshots/vue-setup.png) | ![React Setup](docs/screenshots/react-setup.png) |
| **登录界面** | ![Vue Login](docs/screenshots/vue-login.png) | ![React Login](docs/screenshots/react-login.png) |
| **注册界面** | ![Vue Register](docs/screenshots/vue-register.png) | ![React Register](docs/screenshots/react-register.png) |
| **站内信箱** | ![Vue Outbox](docs/screenshots/vue-outbox.png) | ![React Outbox](docs/screenshots/react-outbox.png) |
| **图形验证码** | ![Vue Captcha](docs/screenshots/vue-captcha.png) | ![React Captcha](docs/screenshots/react-captcha.png) |
| **账号中心** | ![Vue Account](docs/screenshots/vue-account.png) | ![React Account](docs/screenshots/react-account.png) |
| **两步验证 (2FA)** | ![Vue 2FA](docs/screenshots/vue-2fa.png) | ![React 2FA](docs/screenshots/react-2fa.png) |
| **后台用户管理** | ![Vue Admin](docs/screenshots/vue-admin.png) | ![React Admin](docs/screenshots/react-admin.png) |
| **审计日志** | ![Vue Audit](docs/screenshots/vue-audit.png) | ![React Audit](docs/screenshots/react-audit.png) |

---

## 目录结构

```text
examples/demo/
├── run.sh                  # 一键启动运行脚本 (支持 vue/react 及 --dev 参数)
├── Makefile                # 快捷指令 (make run / dev / smoke / ui-packages)
├── API.md                  # 后端接口格式与 HTTP 状态码/错误契约文档
├── README.md               # 本使用指南文档
├── server/                 # FastAPI 演示服务端
│   ├── app.py              # 初始化向导、动态挂载 account-kit 及静态资源托管
│   ├── mailer.py           # 邮件发送器实现 (控制台/SMTP 与内存信箱存储)
│   └── .demo-config.json   # 向导生成的持久化运行配置 (自动生成，已 gitignore)
├── web-vue/                # Vue 3 前端工程 (Vite + Vue Router + account-ui-vue)
│   ├── package.json        # 前端依赖配置 (本地 file: 路径引用 UI 包)
│   └── src/                # 路由、视图页面及 API 客户端集成
├── web-react/              # React 18 前端工程 (Vite + React Router + account-ui-react)
│   ├── package.json        # 前端依赖配置 (本地 file: 路径引用 UI 包)
│   └── src/                # 页面、上下文提供者及路由守卫
├── tests/                  # 端到端冒烟测试套件
│   ├── conftest.py         # 数据库连接 Fixture (解析 DEMO_TEST_DATABASE_URL)
│   └── test_smoke.py       # 自动化冒烟用例 (测试 setup、发码、登录、2FA、审计等完整链路)
└── docs/screenshots/       # 演示截图归档 (Vue 与 React 各 9 张界面图)
```

---

## 冒烟测试运行方法

测试套件直连真实 PostgreSQL 运行，完整校验向导流程与各项认证接口。

1. 配置测试数据库环境变量（支持完整 URL 或拆分参数）：
   ```bash
   # 方式 1：完整连接串
   export DEMO_TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/akdemo_test"

   # 方式 2：分项配置
   # export DEMO_TEST_DB_HOST="127.0.0.1"
   # export DEMO_TEST_DB_PORT="5432"
   # export DEMO_TEST_DB_USER="postgres"
   # export DEMO_TEST_DB_PASSWORD="postgres"
   # export DEMO_TEST_DB_NAME="akdemo_test"
   ```

2. 执行冒烟测试：
   ```bash
   # 位于 examples/demo 目录
   make smoke

   # 或在仓库根目录直接运行 pytest
   python -m pytest examples/demo/tests -q
   ```

> **注意**：
> - 未设置测试数据库变量时，用例会自动 `skip` 跳过。
> - 测试运行时会自动执行 `DROP SCHEMA IF EXISTS auth CASCADE` 以保证每次在干净环境中执行；测试配置会写入临时目录，不会污染开发环境中的 `server/.demo-config.json`。

---

## 常见问题 (FAQ)

### 1. 图形验证码接口报 501 错误？
- **原因**：生成点阵验证码图片需要 `Pillow` 库支持。
- **解决**：在 Python 环境中安装可选依赖：
  ```bash
  pip install "account-kit[captcha]"
  ```
  使用 `./run.sh` 或 `make install` 会自动安装该依赖。

### 2. 前端构建报错找不到 UI 组件包的 dist？
- **原因**：`@kqstone/account-ui-vue` 与 `@kqstone/account-ui-react` 的编译产物 `dist/` 位于 `.gitignore` 中。在全新克隆的仓库中，需先执行构建脚本。
- **解决**：
  `./run.sh` 与 `make run` 已内置自动化处理。如需手动编译，进入对应包目录运行：
  ```bash
  cd packages/account-ui-vue && npm ci && npm run build
  cd packages/account-ui-react && npm ci && npm run build
  ```
  在执行 `npm ci` 时，包内的 `prepare` 钩子（`scripts/prepare-ui.mjs`）也会尝试自动完成 `tsup` 编译。

### 3. 测试频繁或密码连续输错被限流锁定，如何手动清理？
- **原因**：当 `state_backend="db"` 时，登录失败次数与限流计数持久化存储在 PostgreSQL 的 `auth.rate_limit_counters` 数据表中。
- **解决**：在数据库中执行以下 SQL 即可立即清空所有计数与封禁状态：
  ```sql
  TRUNCATE TABLE auth.rate_limit_counters;
  ```

### 4. 本地前端引用报错提示需要 NPM_TOKEN？
- **原因**：生产环境发布的 `@kqstone/account-ui-*` 托管于 GitHub Packages 镜像源，但演示工程中的 `package.json` 采用本地相对路径依赖：
  ```json
  "@kqstone/account-ui-vue": "file:../../../packages/account-ui-vue"
  ```
- **解决**：本地直接执行 `npm install` 即可，**无需**配置任何 GitHub 访问令牌（`NPM_TOKEN`）。

---

## 安全提示

1. **仅用于本地演示与功能评估**：本演示程序设计初衷为功能展示，**严禁将此服务直接暴露在公网环境运行**。
2. **站内信箱仅供 Demo 调试**：`/api/demo/outbox` 接口为了方便本地演示取码，直接将所有发送的验证码明文暴露在内存查询接口中。**严禁在任何生产或正式宿主工程中实现或挂载类似接口**。
3. **生产环境部署建议**：在正式业务中集成 account-kit 时，请通过安全的环境变量或密钥管理服务注入强随机 `jwt_secret`、配置真实的 SMTP 邮件服务，并妥善配置 CORS 跨域白名单。
