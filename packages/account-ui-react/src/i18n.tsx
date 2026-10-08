import { createContext, useContext, type ReactNode } from "react"
import { resolveLocale, type KitLocale } from "./utils"

export type AccountI18nContext = {
  locale: KitLocale
  labels?: unknown
}

const AccountI18nCtx = createContext<AccountI18nContext>({ locale: "zh-CN" })

export function AccountKitProvider({
  locale,
  labels,
  children,
}: {
  locale?: string
  labels?: unknown
  children: ReactNode
}) {
  return (
    <AccountI18nCtx.Provider value={{ locale: resolveLocale(locale), labels }}>
      {children}
    </AccountI18nCtx.Provider>
  )
}

export function useAccountI18n(): AccountI18nContext {
  return useContext(AccountI18nCtx)
}

export function useKitLocale(propLanguage?: string): KitLocale {
  const ctx = useAccountI18n()
  return resolveLocale(propLanguage || ctx.locale)
}

/** Duck-typed i18next: ``language`` plus optional ``languageChanged`` subscribe. */
export function followI18next(i18n: {
  language?: string
  on?(event: string, handler: (lng: string) => void): void
  off?(event: string, handler: (lng: string) => void): void
}) {
  return {
    getLocale: () => resolveLocale(i18n.language),
    subscribe(cb: (locale: KitLocale) => void) {
      const handler = (lng: string) => cb(resolveLocale(lng))
      i18n.on?.("languageChanged", handler)
      return () => i18n.off?.("languageChanged", handler)
    },
  }
}
