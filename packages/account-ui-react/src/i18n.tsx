import { createContext, useCallback, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react"
import type { AccountMessagesOverride } from "./labels"
import { resolveLocale, type KitLocale } from "./utils"

export type I18nLike = {
  language?: string
  on?(event: string, handler: (lng: string) => void): void
  off?(event: string, handler: (lng: string) => void): void
}

export type AccountI18nContext = {
  locale: KitLocale
  messages?: AccountMessagesOverride
}

const AccountI18nCtx = createContext<AccountI18nContext>({ locale: "zh-CN" })

export function AccountKitProvider({
  locale,
  i18n,
  messages,
  labels,
  children,
}: {
  locale?: string
  i18n?: I18nLike
  messages?: AccountMessagesOverride
  /** @deprecated use ``messages`` */
  labels?: AccountMessagesOverride
  children: ReactNode
}) {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!i18n?.on) return () => {}
      const handler = () => onChange()
      i18n.on("languageChanged", handler)
      return () => i18n.off?.("languageChanged", handler)
    },
    [i18n],
  )
  const i18nLocale = useSyncExternalStore(
    subscribe,
    () => resolveLocale(i18n?.language),
    () => resolveLocale(i18n?.language),
  )
  const resolved = i18n ? i18nLocale : resolveLocale(locale)
  const merged = messages ?? labels
  const value = useMemo<AccountI18nContext>(
    () => ({ locale: resolved, messages: merged }),
    [resolved, merged],
  )
  return <AccountI18nCtx.Provider value={value}>{children}</AccountI18nCtx.Provider>
}

export function useAccountI18n(): AccountI18nContext {
  return useContext(AccountI18nCtx)
}

export function useKitLocale(propLanguage?: string): KitLocale {
  const ctx = useAccountI18n()
  return resolveLocale(propLanguage || ctx.locale)
}

/** Duck-typed i18next: ``language`` plus optional ``languageChanged`` subscribe. */
export function followI18next(i18n: I18nLike) {
  return {
    getLocale: () => resolveLocale(i18n.language),
    subscribe(cb: (locale: KitLocale) => void) {
      const handler = (lng: string) => cb(resolveLocale(lng))
      i18n.on?.("languageChanged", handler)
      return () => i18n.off?.("languageChanged", handler)
    },
  }
}
