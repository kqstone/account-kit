import { createContext, createElement, useContext, useMemo, useState, type ReactNode } from "react"
import { AccountKitProvider, resolveLocale, type KitLocale } from "@kqstone/account-ui-react"

export const DEMO_LOCALE_KEY = "ak-demo-locale"

export function readDemoLocale(): KitLocale {
  try {
    return resolveLocale(typeof localStorage !== "undefined" ? localStorage.getItem(DEMO_LOCALE_KEY) : "zh-CN")
  } catch {
    return "zh-CN"
  }
}

export function writeDemoLocale(next: string): KitLocale {
  const loc = resolveLocale(next)
  try {
    localStorage.setItem(DEMO_LOCALE_KEY, loc)
  } catch {
    /* ignore */
  }
  return loc
}

const zh = {
  login: "登录",
  register: "注册",
  reset: "找回密码",
  account: "账号设置",
  adminUsers: "用户管理",
  adminAudit: "审计日志",
  outbox: "站内信箱",
  setup: "初始化向导",
  logout: "退出",
  goLogin: "去登录",
  notInit: "未初始化",
  admin: "管理员",
  drawerMailbox: "侧栏信箱",
  drawerTitle: "打开/关闭右侧站内信箱",
  loginTitle: "登录账号",
  loginDesc: "请输入您的用户名和密码以登录系统",
  forgot: "忘记密码？",
  noAccount: "没有账号？立即注册",
  registerTitle: "注册新账号",
  registerDesc: "请填写账号基本信息并输入邮箱验证码",
  registerHintBefore: "💡 注册验证码已发送至控制台，可在",
  registerHintAfter: "中实时查看并一键复制。",
  haveAccount: "已有账号？",
  goLoginNow: "立即登录",
  resetTitle: "找回密码",
  resetDesc: "输入注册邮箱获取验证码，并设置新密码",
  resetHintBefore: "💡 重置密码验证码可在",
  resetHintAfter: "中查看。",
  resetOk: "🎉 密码重置成功！请使用新密码重新登录。",
  backLogin: "返回登录",
  registerAccount: "注册账号",
  goLoginBtn: "前往登录",
  mfaExpired: "两步验证已过期，请重新登录",
  emailLabel: "邮箱",
  roleLabel: "角色",
  roleDefault: "默认",
  notFoundTitle: "页面不存在",
  notFoundBody: "抱歉，您访问的页面不存在或已被移除。",
  backHome: "返回首页",
  langZh: "中文",
  langEn: "English",
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
  admin: "Admin",
  drawerMailbox: "Inbox",
  drawerTitle: "Toggle the code inbox drawer",
  loginTitle: "Sign in",
  loginDesc: "Enter your username and password",
  forgot: "Forgot password?",
  noAccount: "No account? Register",
  registerTitle: "Create an account",
  registerDesc: "Fill in the basics and the email code",
  registerHintBefore: "💡 Codes also go to the console; open the",
  registerHintAfter: "to copy them.",
  haveAccount: "Already have an account?",
  goLoginNow: "Sign in",
  resetTitle: "Reset password",
  resetDesc: "Send a code to your email and set a new password",
  resetHintBefore: "💡 Reset codes are in the",
  resetHintAfter: ".",
  resetOk: "Password reset. Sign in with the new password.",
  backLogin: "Back to sign in",
  registerAccount: "Register",
  goLoginBtn: "Go to sign in",
  mfaExpired: "Two-factor verification expired, please sign in again",
  emailLabel: "Email",
  roleLabel: "Role",
  roleDefault: "default",
  notFoundTitle: "Page not found",
  notFoundBody: "This page does not exist or was removed.",
  backHome: "Back home",
  langZh: "中文",
  langEn: "English",
}

export type DemoMessages = typeof zh
export const demoMessages: Record<KitLocale, DemoMessages> = { "zh-CN": zh, en }

type DemoI18nValue = {
  locale: KitLocale
  setLocale: (next: string) => void
  t: DemoMessages
}

const DemoI18nContext = createContext<DemoI18nValue>({
  locale: "zh-CN",
  setLocale: () => undefined,
  t: zh,
})

export function DemoI18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<KitLocale>(readDemoLocale)
  const value = useMemo<DemoI18nValue>(
    () => ({
      locale,
      setLocale(next: string) {
        setLocaleState(writeDemoLocale(next))
      },
      t: demoMessages[locale],
    }),
    [locale],
  )
  return createElement(
    DemoI18nContext.Provider,
    { value },
    createElement(AccountKitProvider, { locale, children }),
  )
}

export function useDemoI18n() {
  return useContext(DemoI18nContext)
}
