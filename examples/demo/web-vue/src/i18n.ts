import { computed, ref } from "vue"
import { resolveLocale, type KitLocale } from "@kqstone/account-ui-vue"

export const DEMO_LOCALE_KEY = "ak-demo-locale"

function readStored(): KitLocale {
  try {
    return resolveLocale(localStorage.getItem(DEMO_LOCALE_KEY))
  } catch {
    return "zh-CN"
  }
}

export const demoLocale = ref<KitLocale>(readStored())

export function setDemoLocale(next: string) {
  const loc = resolveLocale(next)
  demoLocale.value = loc
  try {
    localStorage.setItem(DEMO_LOCALE_KEY, loc)
  } catch {
    /* ignore */
  }
}

const zh = {
  login: "登录",
  register: "注册",
  reset: "找回密码",
  account: "账号中心",
  adminUsers: "用户管理",
  adminAudit: "审计日志",
  outbox: "站内信箱",
  setup: "初始化向导",
  logout: "退出",
  goLogin: "去登录",
  notInit: "未初始化",
  connected: "已连接",
  admin: "管理员",
  drawerMailbox: "验证码信箱",
  drawerTitle: "打开右侧站内信箱抽屉",
  loginTitle: "登录账号",
  loginDesc: "输入用户名与密码登录 account-kit 演示系统",
  loginHint: "如果账号开启了邮箱 2FA，请在信箱获取验证码",
  viewMailbox: "查看信箱",
  registerLink: "注册新账号",
  forgot: "忘记密码？",
  registerTitle: "注册新账号",
  registerDesc: "创建您的演示账号，体验完整的注册与审批流程",
  registerHint: "点击「发送验证码」后，可在信箱中查看",
  haveAccount: "已有账号？",
  goLoginNow: "立即登录",
  resetTitle: "找回密码",
  resetDesc: "输入绑定的邮箱获取重置验证码并设置新密码",
  resetHint: "发送验证码后，可在右侧信箱中复制使用",
  rememberPassword: "想起密码了？",
  backLogin: "返回登录",
  goLoginBtn: "前往登录",
  mfaExpired: "两步验证已过期，请重新登录",
  approved: "已通过审批",
  pending: "审批中",
  emailLabel: "邮箱",
  roleLabel: "角色",
  roleDefault: "默认",
  logoutAll: "全部设备登出",
  langZh: "中文",
  langEn: "English",
  mailboxItems: "条",
  refresh: "刷新",
  refreshing: "刷新中…",
  autoRefresh: "自动刷新 (3s)",
  searchMailbox: "搜索邮箱或用途…",
}

const en = {
  login: "Sign in",
  register: "Register",
  reset: "Reset password",
  account: "Account",
  adminUsers: "Users",
  adminAudit: "Audit log",
  outbox: "Inbox",
  setup: "Setup",
  logout: "Sign out",
  goLogin: "Sign in",
  notInit: "Not initialized",
  connected: "Connected",
  admin: "Admin",
  drawerMailbox: "Codes",
  drawerTitle: "Toggle the code inbox drawer",
  loginTitle: "Sign in",
  loginDesc: "Enter your username and password to use the account-kit demo",
  loginHint: "If email 2FA is on, copy the code from the inbox",
  viewMailbox: "Open inbox",
  registerLink: "Create an account",
  forgot: "Forgot password?",
  registerTitle: "Create an account",
  registerDesc: "Register a demo account and try the approval flow",
  registerHint: "After you send a code, open the inbox to copy it",
  haveAccount: "Already have an account?",
  goLoginNow: "Sign in",
  resetTitle: "Reset password",
  resetDesc: "Send a code to the bound email and set a new password",
  resetHint: "After sending, copy the code from the inbox on the right",
  rememberPassword: "Remembered your password?",
  backLogin: "Back to sign in",
  goLoginBtn: "Go to sign in",
  mfaExpired: "Two-factor verification expired, please sign in again",
  approved: "Approved",
  pending: "Pending",
  emailLabel: "Email",
  roleLabel: "Role",
  roleDefault: "default",
  logoutAll: "Sign out everywhere",
  langZh: "中文",
  langEn: "English",
  mailboxItems: "items",
  refresh: "Refresh",
  refreshing: "Refreshing…",
  autoRefresh: "Auto refresh (3s)",
  searchMailbox: "Search email or purpose…",
}

export type DemoMessages = typeof zh

export const messages: Record<KitLocale, DemoMessages> = { "zh-CN": zh, en }

export const tt = computed(() => messages[demoLocale.value])
