/**
 * 0.6.0: styles for AuthShell and CodeInputRow. Shared verbatim by the React and Vue packages.
 * Every selector is scoped under `.ak-shell*` or `.ak-code-*` / `.ak-field-label`; no bare
 * input/button/select rules, so Element Plus / antd controls placed in the slot are untouched.
 * Theme through CSS variables (set them on :root, on `.ak-shell`, or via the `style` prop):
 * --ak-shell-bg, --ak-shell-admin-bg, --ak-shell-primary, --ak-shell-card-bg, --ak-shell-card-radius,
 * --ak-shell-card-width, --ak-shell-card-shadow, --ak-shell-card-padding, --ak-shell-text,
 * --ak-shell-muted, --ak-shell-brand-text, --ak-shell-gap, --ak-safe-top/right/bottom/left,
 * --ak-control-height.
 */
export const CODE_ROW_CSS = `
.ak-code-field{display:flex;flex-direction:column;gap:4px;font-size:14px}
.ak-field-label{font-size:14px}
.ak-code-row{display:flex;flex-wrap:nowrap;align-items:flex-end;gap:8px;width:100%;box-sizing:border-box}
.ak-code-row>.ak-code-input{flex:1 1 auto;min-width:0;width:auto;height:var(--ak-control-height,40px);margin:0;box-sizing:border-box}
.ak-code-row>.ak-code-btn{flex:0 0 auto;min-width:96px;height:var(--ak-control-height,40px);margin:0;padding:0 12px;white-space:nowrap;box-sizing:border-box;line-height:1}
.ak-code-row>.ak-code-img{flex:0 0 auto;display:block;height:var(--ak-control-height,40px);border-radius:8px;cursor:pointer;box-sizing:border-box}
`

export const SHELL_CSS = `
.ak-shell{display:flex;flex-direction:column;width:100%;height:100vh;height:100dvh;max-height:100dvh;overflow:hidden;position:relative;box-sizing:border-box;background:var(--ak-shell-bg,linear-gradient(135deg,#334155 0%,#64748b 100%));color:var(--ak-shell-text,#101828);padding:var(--ak-safe-top,env(safe-area-inset-top,0px)) var(--ak-safe-right,env(safe-area-inset-right,0px)) var(--ak-safe-bottom,env(safe-area-inset-bottom,0px)) var(--ak-safe-left,env(safe-area-inset-left,0px));font-family:inherit}
.ak-shell--admin{background:var(--ak-shell-admin-bg,var(--ak-shell-bg,linear-gradient(135deg,#0f172a 0%,#334155 100%)))}
.ak-shell-lang{position:absolute;z-index:10;top:calc(14px + var(--ak-safe-top,env(safe-area-inset-top,0px)));right:calc(16px + var(--ak-safe-right,env(safe-area-inset-right,0px)))}
.ak-shell-header{flex-shrink:0;display:flex;flex-direction:column;align-items:center;width:100%;padding:14px 16px 6px;box-sizing:border-box;position:relative}
.ak-shell-brand{width:100%;max-width:var(--ak-shell-card-width,420px);text-align:center;user-select:none;color:var(--ak-shell-brand-text,#fff)}
.ak-shell-brand.is-clickable{cursor:pointer}
.ak-shell-brand.is-clickable:focus-visible{outline:2px solid rgba(255,255,255,.8);outline-offset:4px;border-radius:8px}
.ak-shell-logo{width:48px;height:48px;margin:0 auto 8px;display:flex;align-items:center;justify-content:center;border-radius:14px;background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.18);box-shadow:0 8px 32px rgba(15,23,42,.25);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-sizing:border-box;overflow:hidden}
.ak-shell-brand-name{margin:0;font-size:20px;line-height:1.3;font-weight:700;letter-spacing:-.5px}
.ak-shell-brand-subtitle{margin:2px 0 0;font-size:13px;opacity:.85}
.ak-shell-main{flex:1 1 0%;min-height:0;display:flex;flex-direction:column;align-items:center;width:100%;padding:4px var(--ak-shell-gap,16px) 8px;box-sizing:border-box;overflow:hidden}
.ak-shell.is-native .ak-shell-main,.ak-shell.no-copyright .ak-shell-main{padding-bottom:var(--ak-shell-gap,16px)}
.ak-shell-card{width:100%;max-width:var(--ak-shell-card-width,420px);max-height:100%;margin:auto 0;display:flex;flex-direction:column;overflow:hidden;box-sizing:border-box;background:var(--ak-shell-card-bg,#fff);border-radius:var(--ak-shell-card-radius,16px);box-shadow:var(--ak-shell-card-shadow,0 20px 25px -5px rgba(0,0,0,.1),0 10px 10px -5px rgba(0,0,0,.04));padding:var(--ak-shell-card-padding,24px);color:var(--ak-shell-text,#101828)}
.ak-shell-card-header{flex-shrink:0;text-align:center;margin-bottom:16px}
.ak-shell-title{margin:0;font-size:20px;line-height:1.3;font-weight:700}
.ak-shell-subtitle{margin:4px 0 0;font-size:14px;color:var(--ak-shell-muted,#667085)}
.ak-shell-body{flex:1 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;-webkit-overflow-scrolling:touch}
.ak-shell-body>.ak-form{max-width:none}
.ak-shell-body .ak-form button:not(.ak-link):not(.ak-code-btn){background:var(--ak-shell-primary,#2563eb)}
.ak-shell-body .ak-form .ak-code-row>.ak-code-btn{background:transparent;color:var(--ak-shell-primary,#2563eb);border:1px solid var(--ak-shell-primary,#2563eb)}
.ak-shell-card-footer{flex-shrink:0;margin-top:16px;text-align:center;font-size:14px;color:var(--ak-shell-muted,#667085)}
.ak-shell-card-footer a{color:var(--ak-shell-primary,#2563eb);text-decoration:none}
.ak-shell-footer{flex-shrink:0;padding:8px 16px 12px;text-align:center;font-size:12px;line-height:1.5;color:rgba(255,255,255,.75)}
@media (max-height:680px){.ak-shell-header{padding-top:8px;padding-bottom:4px}.ak-shell-logo{width:40px;height:40px;margin-bottom:4px}.ak-shell-brand-name{font-size:18px}.ak-shell-card{padding:16px}.ak-shell-card-header{margin-bottom:12px}.ak-shell-footer{padding:4px 16px 8px}}
`

export function ensureShellStyle() {
  if (typeof document === "undefined" || document.getElementById("account-kit-shell")) return
  const style = document.createElement("style")
  style.id = "account-kit-shell"
  style.textContent = CODE_ROW_CSS + SHELL_CSS
  document.head.appendChild(style)
}

/** True on a Capacitor native platform (Android/iOS app). Tauri and plain web return false. */
export function detectNative(): boolean {
  try {
    const cap = (globalThis as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor
    return Boolean(cap?.isNativePlatform?.())
  } catch {
    return false
  }
}

/** The system/browser language (e.g. "zh-CN"), for hosts that follow the OS language on native. */
export function systemLocale(fallback = "en"): string {
  if (typeof navigator === "undefined") return fallback
  return (navigator.languages && navigator.languages[0]) || navigator.language || fallback
}
