import { defineComponent, h, onBeforeUnmount, onMounted, ref, watch, type PropType } from "vue"
import { ensureAccountStyle, type AccountClient, type AccountUser } from "./client"
import { resolveProfileLabels, type ProfileLabels } from "./labels"
import { errorCodeOf, initialsOf, interpolate, messageOf, textOf, type DeepPartial } from "./utils"

export type GenderFallbacks = { male?: string; female?: string; unspecified?: string }

function fallbackSrcOf(
  user: AccountUser | { gender?: string | null } | null | undefined,
  genderFallbacks?: GenderFallbacks | null,
  fallbackSrc?: string,
) {
  if (fallbackSrc) return fallbackSrc
  const gender = user?.gender
  if (gender === "male" && genderFallbacks?.male) return genderFallbacks.male
  if (gender === "female" && genderFallbacks?.female) return genderFallbacks.female
  return genderFallbacks?.unspecified || ""
}

export const UserAvatar = defineComponent({
  name: "UserAvatar",
  props: {
    user: { type: Object as PropType<AccountUser | null>, default: null },
    src: { type: String, default: "" },
    size: { type: Number, default: 48 },
    token: { type: String, default: "" },
    client: { type: Object as PropType<AccountClient>, default: null },
    fallbackSrc: { type: String, default: "" },
    genderFallbacks: { type: Object as PropType<GenderFallbacks>, default: null },
    alt: { type: String, default: "" },
    className: { type: String, default: "" },
  },
  setup(props, { attrs }) {
    ensureAccountStyle()
    const blobUrl = ref("")

    async function loadBlob() {
      if (blobUrl.value) {
        URL.revokeObjectURL(blobUrl.value)
        blobUrl.value = ""
      }
      if (props.src) return
      const userId = props.user?.id
      if (!props.user?.has_custom_avatar || !props.client || !props.token || !userId) return
      try {
        const blob = await props.client.avatarBlob(userId, props.token)
        blobUrl.value = URL.createObjectURL(blob)
      } catch {
        blobUrl.value = ""
      }
    }

    onMounted(() => void loadBlob())
    watch(
      () => [props.src, props.user?.id, props.user?.has_custom_avatar, props.token, props.client],
      () => void loadBlob(),
    )
    onBeforeUnmount(() => {
      if (blobUrl.value) URL.revokeObjectURL(blobUrl.value)
    })

    return () => {
      const fallback = fallbackSrcOf(props.user, props.genderFallbacks, props.fallbackSrc)
      const image = props.src || blobUrl.value || fallback
      const size = props.size || 48
      const label = props.alt || props.user?.full_name || props.user?.username || "avatar"
      const cls = ["ak-avatar", props.className, typeof attrs.class === "string" ? attrs.class : ""].filter(Boolean).join(" ")
      return h(
        "span",
        { class: cls, style: { width: `${size}px`, height: `${size}px`, fontSize: `${Math.max(12, size / 2.4)}px` }, title: label },
        image ? [h("img", { src: image, alt: label })] : [initialsOf(props.user)],
      )
    }
  },
})

export const AvatarUploader = defineComponent({
  name: "AvatarUploader",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, required: true },
    user: { type: Object as PropType<AccountUser | null>, default: null },
    language: { type: String, default: "zh" },
    labels: { type: Object as PropType<DeepPartial<ProfileLabels>>, default: null },
    size: { type: Number, default: 72 },
    accept: { type: String, default: "image/jpeg,image/png,image/webp" },
    fallbackSrc: { type: String, default: "" },
    genderFallbacks: { type: Object as PropType<GenderFallbacks>, default: null },
    className: { type: String, default: "" },
    prepareFile: { type: Function as PropType<(file: File) => Promise<Blob | File> | Blob | File>, default: undefined },
  },
  emits: ["uploaded", "deleted", "error"],
  setup(props, { emit, slots, attrs }) {
    ensureAccountStyle()
    const busy = ref(false)
    const error = ref("")
    const inputEl = ref<HTMLInputElement | null>(null)
    const current = ref<AccountUser | null>(props.user)
    watch(
      () => props.user,
      (value) => {
        current.value = value
      },
    )

    const L = () => resolveProfileLabels(props.language, props.labels)

    async function upload(file: File) {
      busy.value = true
      error.value = ""
      try {
        const prepared = props.prepareFile ? await props.prepareFile(file) : file
        const user = await props.client.uploadAvatar(props.token, prepared, file.name)
        current.value = user
        emit("uploaded", user)
      } catch (e) {
        error.value = messageOf(e, L().error)
        emit("error", e)
      } finally {
        busy.value = false
      }
    }

    async function remove() {
      busy.value = true
      error.value = ""
      try {
        const user = await props.client.deleteAvatar(props.token)
        current.value = user
        emit("deleted", user)
      } catch (e) {
        error.value = messageOf(e, L().error)
        emit("error", e)
      } finally {
        busy.value = false
      }
    }

    return () => {
      const labels = L()
      const cls = ["ak-avatar-uploader", props.className, typeof attrs.class === "string" ? attrs.class : ""].filter(Boolean).join(" ")
      return h("div", { class: cls }, [
        h("input", {
          ref: (el) => {
            inputEl.value = el as HTMLInputElement | null
          },
          type: "file",
          accept: props.accept,
          style: "display:none",
          onChange: (event: Event) => {
            const file = (event.target as HTMLInputElement).files?.[0]
            ;(event.target as HTMLInputElement).value = ""
            if (file) void upload(file)
          },
        }),
        h(
          "button",
          {
            type: "button",
            class: "ak-avatar-btn",
            disabled: busy.value,
            title: labels.uploadAvatar,
            onClick: () => inputEl.value?.click(),
          },
          [
            slots.avatar?.({ user: current.value, busy: busy.value }) ||
              h(UserAvatar, {
                user: current.value,
                client: props.client,
                token: props.token,
                size: props.size,
                fallbackSrc: props.fallbackSrc,
                genderFallbacks: props.genderFallbacks,
              }),
          ],
        ),
        h("div", [
          h("p", { class: "ak-muted" }, busy.value ? labels.uploading : labels.avatarHint),
          current.value?.has_custom_avatar
            ? h("button", { type: "button", class: "ak-btn ak-btn-outline ak-btn-small", disabled: busy.value, onClick: () => void remove() }, labels.deleteAvatar)
            : null,
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
        ]),
      ])
    }
  },
})

export const ProfileFields = defineComponent({
  name: "ProfileFields",
  props: {
    client: { type: Object as PropType<AccountClient>, required: true },
    token: { type: String, required: true },
    user: { type: Object as PropType<AccountUser | null>, default: null },
    language: { type: String, default: "zh" },
    labels: { type: Object as PropType<DeepPartial<ProfileLabels>>, default: null },
    showChangePassword: { type: Boolean, default: true },
    /**
     * Email code for password changes (server ``change_password_require_email_code``):
     * ``true`` always shows the code field, ``"auto"`` (default) shows it once the server
     * answers ``EMAIL_CODE_REQUIRED``, ``false`` never.
     */
    passwordEmailCode: { type: [Boolean, String] as PropType<boolean | "auto">, default: "auto" },
    className: { type: String, default: "" },
  },
  emits: ["saved", "password-changed"],
  setup(props, { emit, slots, attrs }) {
    ensureAccountStyle()
    const fullName = ref(props.user?.full_name || "")
    const institution = ref(props.user?.institution || "")
    const gender = ref(props.user?.gender || "")
    const birth = ref(props.user?.birth_year_month || "")
    const oldPassword = ref("")
    const newPassword = ref("")
    const confirmPassword = ref("")
    const emailCode = ref("")
    const codeNeeded = ref(false)
    const sending = ref(false)
    const cooldown = ref(0)
    let cooldownTimer: ReturnType<typeof setInterval> | null = null
    const error = ref("")
    const info = ref("")
    const busy = ref(false)
    onBeforeUnmount(() => {
      if (cooldownTimer) clearInterval(cooldownTimer)
    })
    const showCode = () => props.passwordEmailCode === true || (props.passwordEmailCode === "auto" && codeNeeded.value)

    async function sendPasswordCode() {
      const labels = L()
      const email = props.user?.email
      if (!email) return
      error.value = ""
      sending.value = true
      try {
        await props.client.sendCode(email, "change_password", props.language, props.token)
        info.value = interpolate(labels.codeSentTo, { email })
        cooldown.value = 60
        if (cooldownTimer) clearInterval(cooldownTimer)
        cooldownTimer = setInterval(() => {
          cooldown.value -= 1
          if (cooldown.value <= 0 && cooldownTimer) {
            clearInterval(cooldownTimer)
            cooldownTimer = null
          }
        }, 1000)
      } catch (e) {
        error.value = messageOf(e, labels.error)
      } finally {
        sending.value = false
      }
    }

    watch(
      () => props.user,
      (user) => {
        fullName.value = user?.full_name || ""
        institution.value = user?.institution || ""
        gender.value = user?.gender || ""
        birth.value = user?.birth_year_month || ""
      },
    )

    const L = () => resolveProfileLabels(props.language, props.labels)

    async function submit() {
      const labels = L()
      error.value = ""
      info.value = ""
      if (newPassword.value && newPassword.value !== confirmPassword.value) {
        error.value = labels.passwordMismatch
        return
      }
      busy.value = true
      try {
        const patched = await props.client.patchMe(props.token, {
          full_name: fullName.value.trim() || null,
          institution: institution.value.trim() || null,
          gender: gender.value || null,
          birth_year_month: birth.value || null,
        })
        emit("saved", patched)
        if (newPassword.value) {
          try {
            await props.client.changePassword(props.token, oldPassword.value, newPassword.value, emailCode.value.trim() || undefined)
          } catch (e) {
            if (errorCodeOf(e) === "EMAIL_CODE_REQUIRED" && props.passwordEmailCode !== false) {
              codeNeeded.value = true
              error.value = labels.passwordEmailCodeHint
              return
            }
            throw e
          }
          oldPassword.value = ""
          newPassword.value = ""
          confirmPassword.value = ""
          emailCode.value = ""
          emit("password-changed")
          info.value = labels.passwordChanged
        } else {
          info.value = labels.saved
        }
      } catch (e) {
        error.value = messageOf(e, labels.error)
      } finally {
        busy.value = false
      }
    }

    return () => {
      const labels = L()
      const cls = ["ak-form", props.className, typeof attrs.class === "string" ? attrs.class : ""].filter(Boolean).join(" ")
      return h(
        "form",
        {
          class: cls,
          onSubmit: (event: Event) => {
            event.preventDefault()
            void submit()
          },
        },
        [
          h("label", [labels.fullName, h("input", { value: fullName.value, autocomplete: "name", onInput: (event: Event) => { fullName.value = textOf(event) } })]),
          h("label", [labels.institution, h("input", { value: institution.value, onInput: (event: Event) => { institution.value = textOf(event) } })]),
          h("label", [
            labels.gender,
            h("select", { value: gender.value, onChange: (event: Event) => { gender.value = textOf(event) } }, [
              h("option", { value: "" }, labels.genderUnspecified),
              h("option", { value: "male" }, labels.genderMale),
              h("option", { value: "female" }, labels.genderFemale),
            ]),
          ]),
          h("label", [labels.birth, h("input", { type: "month", value: birth.value, onInput: (event: Event) => { birth.value = textOf(event) } })]),
          props.showChangePassword
            ? [
                h("h3", { style: "margin:8px 0 0;font-size:15px" }, labels.changePassword),
                h("label", [labels.oldPassword, h("input", { type: "password", value: oldPassword.value, autocomplete: "current-password", onInput: (event: Event) => { oldPassword.value = textOf(event) } })]),
                h("label", [labels.newPassword, h("input", { type: "password", value: newPassword.value, autocomplete: "new-password", onInput: (event: Event) => { newPassword.value = textOf(event) } })]),
                h("label", [labels.confirmPassword, h("input", { type: "password", value: confirmPassword.value, autocomplete: "new-password", onInput: (event: Event) => { confirmPassword.value = textOf(event) } })]),
                showCode()
                  ? h("label", [
                      labels.emailCode,
                      h("span", { class: "ak-row" }, [
                        h("input", { class: "ak-input", value: emailCode.value, maxlength: 6, inputmode: "numeric", autocomplete: "one-time-code", placeholder: labels.emailCodePlaceholder, onInput: (event: Event) => { emailCode.value = textOf(event) } }),
                        h(
                          "button",
                          { type: "button", disabled: sending.value || cooldown.value > 0 || !props.user?.email, onClick: () => void sendPasswordCode() },
                          sending.value ? labels.sending : cooldown.value > 0 ? interpolate(labels.resendIn, { s: cooldown.value }) : labels.sendCode,
                        ),
                      ]),
                    ])
                  : null,
              ]
            : null,
          slots.default?.(),
          error.value ? h("p", { class: "ak-error" }, error.value) : null,
          info.value ? h("p", { class: "ak-success" }, info.value) : null,
          h("button", { type: "submit", disabled: busy.value }, busy.value ? labels.saving : labels.save),
        ],
      )
    }
  },
})
