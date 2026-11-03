import { createApp, defineComponent, h, ref } from "vue"
import { AuthShell, CodeInputRow, LoginForm, RegisterForm, ResetPasswordForm } from "../../packages/account-ui-vue/src/index"
import { mockClient } from "./mockClient"

const q = new URLSearchParams(location.search)
const page = q.get("page") || "login"
const native = q.has("native")

const Admin = defineComponent(() => {
  const code = ref("")
  return () =>
    h("form", { class: "ak-form" }, [
      h("label", ["用户名", h("input")]),
      h("label", ["密码", h("input", { type: "password" })]),
      h(CodeInputRow, { label: "验证码", modelValue: code.value, maxlength: 6, inputmode: "numeric", buttonText: "发送验证码", "onUpdate:modelValue": (v: string) => (code.value = v) }),
      h("button", { type: "submit" }, "登录"),
    ])
})

const App = defineComponent(() => () => {
  const props: Record<string, unknown> = { brandName: "Account Kit", copyright: "© 2026 Account Kit", native }
  const slots: Record<string, () => unknown> = {
    logo: () => h("span", { style: "color:#fff;font-weight:700;font-size:22px" }, "A"),
    lang: () => h("button", { style: "background:rgba(255,255,255,.2);color:#fff;border:0;border-radius:6px;padding:4px 8px" }, "中 / EN"),
  }
  if (page === "register") return h(AuthShell, { ...props, title: "注册" }, { ...slots, footer: () => h("a", { href: "#" }, "已有账号？登录"), default: () => h(RegisterForm, { client: mockClient }) })
  if (page === "reset") return h(AuthShell, { ...props, title: "找回密码" }, { ...slots, footer: () => h("a", { href: "#" }, "返回登录"), default: () => h(ResetPasswordForm, { client: mockClient }) })
  if (page === "admin") return h(AuthShell, { ...props, variant: "admin", brandName: "系统管理", brandSubtitle: "管理员控制台", title: "管理员登录" }, { ...slots, default: () => h(Admin) })
  return h(AuthShell, { ...props, title: "登录" }, { ...slots, footer: () => h("span", [h("a", { href: "#" }, "注册"), " · ", h("a", { href: "#" }, "忘记密码")]), default: () => h(LoginForm, { client: mockClient }) })
})
createApp(App).mount("#app")
