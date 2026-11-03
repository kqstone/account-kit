import { useId, type CSSProperties, type HTMLAttributes, type KeyboardEvent, type ReactNode } from "react"
import { ensureAccountStyle } from "./client"
import { detectNative, ensureShellStyle } from "./shellStyle"

export type AuthShellProps = {
  brandName?: ReactNode
  brandSubtitle?: ReactNode
  /** Logo node rendered inside the 48px glass box. Omit to hide the box. */
  logo?: ReactNode
  onBrandClick?: () => void
  title?: ReactNode
  subtitle?: ReactNode
  /** Fixed card footer (links). */
  footer?: ReactNode
  /** Rendered outside the scroll flow (modals etc.). */
  extra?: ReactNode
  copyright?: ReactNode
  showCopyright?: boolean
  /** Host-provided language switch component. */
  languageSwitch?: ReactNode
  showLanguageSwitch?: boolean
  /** Defaults to detectNative() (Capacitor native platform). */
  native?: boolean
  variant?: "user" | "admin"
  /** Extra attributes for <header>, e.g. { "data-tauri-drag-region": "" }. */
  headerAttrs?: HTMLAttributes<HTMLElement> & Record<string, unknown>
  className?: string
  style?: CSSProperties
  cardClassName?: string
  cardStyle?: CSSProperties
  /** The only scrollable region. */
  children?: ReactNode
}

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ")
}

export function AuthShell(props: AuthShellProps) {
  ensureShellStyle()
  const native = props.native ?? detectNative()
  const showLang = (props.showLanguageSwitch ?? !native) && props.languageSwitch != null
  const showCopy = (props.showCopyright ?? !native) && props.copyright != null
  const hasHeader = props.title != null || props.subtitle != null
  const clickable = typeof props.onBrandClick === "function"
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      props.onBrandClick?.()
    }
  }
  const hasBrand = props.logo != null || props.brandName != null || props.brandSubtitle != null
  return (
    <div
      className={cx("ak-shell", `ak-shell--${props.variant ?? "user"}`, native ? "is-native" : "is-web", showCopy ? "has-copyright" : "no-copyright", props.className)}
      style={props.style}
    >
      {showLang ? <div className="ak-shell-lang">{props.languageSwitch}</div> : null}
      <header {...(props.headerAttrs ?? {})} className={cx("ak-shell-header", props.headerAttrs?.className as string | undefined)}>
        {hasBrand ? (
          <div
            className={cx("ak-shell-brand", clickable && "is-clickable")}
            role={clickable ? "button" : undefined}
            tabIndex={clickable ? 0 : undefined}
            onClick={clickable ? () => props.onBrandClick?.() : undefined}
            onKeyDown={clickable ? onKeyDown : undefined}
          >
            {props.logo != null ? <div className="ak-shell-logo">{props.logo}</div> : null}
            {props.brandName != null ? <div className="ak-shell-brand-name">{props.brandName}</div> : null}
            {props.brandSubtitle != null ? <div className="ak-shell-brand-subtitle">{props.brandSubtitle}</div> : null}
          </div>
        ) : null}
      </header>
      <main className="ak-shell-main">
        <div className={cx("ak-shell-card", props.cardClassName)} style={props.cardStyle}>
          {hasHeader ? (
            <div className="ak-shell-card-header">
              {props.title != null ? <h1 className="ak-shell-title">{props.title}</h1> : null}
              {props.subtitle != null ? <p className="ak-shell-subtitle">{props.subtitle}</p> : null}
            </div>
          ) : null}
          <div className="ak-shell-body">{props.children}</div>
          {props.footer != null ? <div className="ak-shell-card-footer">{props.footer}</div> : null}
        </div>
      </main>
      {showCopy ? <footer className="ak-shell-footer">{props.copyright}</footer> : null}
      {props.extra}
    </div>
  )
}

export type CodeInputRowProps = {
  label?: ReactNode
  value: string
  onChange: (value: string) => void
  placeholder?: string
  maxLength?: number
  inputMode?: HTMLAttributes<HTMLInputElement>["inputMode"]
  autoComplete?: string
  name?: string
  /** Optional captcha image shown between input and button. */
  imageSrc?: string
  imageAlt?: string
  onImageClick?: () => void
  buttonText?: ReactNode
  buttonDisabled?: boolean
  /** Hide the button (e.g. captcha image only). */
  hideButton?: boolean
  onButtonClick?: () => void
  className?: string
  /** Extra content after the row (errors, hints). */
  children?: ReactNode
}

export function CodeInputRow(props: CodeInputRowProps) {
  ensureAccountStyle()
  const id = useId()
  return (
    <div className={cx("ak-field", "ak-code-field", props.className)}>
      {props.label != null ? (
        <label className="ak-field-label" htmlFor={id}>
          {props.label}
        </label>
      ) : null}
      <div className="ak-code-row ak-row">
        <input
          id={id}
          className="ak-input ak-code-input"
          name={props.name}
          value={props.value}
          maxLength={props.maxLength}
          inputMode={props.inputMode}
          autoComplete={props.autoComplete ?? "off"}
          placeholder={props.placeholder}
          onChange={(event) => props.onChange(event.target.value)}
        />
        {props.imageSrc ? (
          <img className="ak-code-img" src={props.imageSrc} alt={props.imageAlt ?? "captcha"} onClick={() => props.onImageClick?.()} />
        ) : null}
        {props.hideButton ? null : (
          <button type="button" className="ak-code-btn" disabled={props.buttonDisabled} onClick={() => props.onButtonClick?.()}>
            {props.buttonText}
          </button>
        )}
      </div>
      {props.children}
    </div>
  )
}
