import { computed, inject, provide, unref, type App, type InjectionKey, type MaybeRef, type Ref } from "vue"
import type { AccountMessagesOverride } from "./labels"
import { resolveLocale, type KitLocale } from "./utils"

export type AccountI18nSource = string | Ref<string> | (() => string)

export type VueI18nLike = { global?: { locale?: unknown }; locale?: unknown }

export type AccountI18nContext = {
  locale: () => string
  messages?: AccountMessagesOverride
}

export const ACCOUNT_I18N_KEY: InjectionKey<AccountI18nContext> = Symbol("account-kit-i18n")

function readLocale(source?: AccountI18nSource | null): string {
  if (source == null) return "zh-CN"
  if (typeof source === "function") return source()
  return unref(source)
}

export function provideAccountI18n(locale: AccountI18nSource, messages?: AccountMessagesOverride) {
  provide(ACCOUNT_I18N_KEY, { locale: () => readLocale(locale), messages })
}

export function useAccountI18n() {
  const ctx = inject(ACCOUNT_I18N_KEY, null)
  const locale = computed<KitLocale>(() => resolveLocale(ctx?.locale()))
  return { locale, messages: ctx?.messages }
}

export function useKitLocale(propLanguage?: MaybeRef<string | undefined> | (() => string | undefined)) {
  const ctx = inject(ACCOUNT_I18N_KEY, null)
  return computed<KitLocale>(() => {
    const raw = typeof propLanguage === "function" ? propLanguage() : unref(propLanguage)
    return resolveLocale(raw || ctx?.locale())
  })
}

/** Duck-typed vue-i18n: reads ``global.locale`` or ``locale`` (string / Ref / getter). */
export function followVueI18n(i18n: VueI18nLike): () => string {
  return () => {
    const raw = (i18n as { global?: { locale?: unknown } }).global?.locale ?? i18n.locale
    if (typeof raw === "function") return resolveLocale((raw as () => string)())
    return resolveLocale(unref(raw as string | Ref<string> | undefined))
  }
}

export function accountKitI18n(options?: {
  locale?: AccountI18nSource
  i18n?: VueI18nLike
  messages?: AccountMessagesOverride
  /** @deprecated use ``messages`` */
  labels?: AccountMessagesOverride
}) {
  const localeSource: AccountI18nSource | undefined = options?.i18n ? followVueI18n(options.i18n) : options?.locale
  const messages = options?.messages ?? options?.labels
  return {
    install(app: App) {
      app.provide(ACCOUNT_I18N_KEY, {
        locale: () => readLocale(localeSource),
        messages,
      })
    },
  }
}
