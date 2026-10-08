import { useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type ReactNode } from "react"
import { ensureAccountStyle, type AccountClient, type AccountUser, type ProfileUpdateResult } from "./client"
import { useKitLocale } from "./i18n"
import { resolveProfileLabels, type ProfileLabels } from "./labels"
import { useCountdown } from "./security"
import { errorCodeOf, initialsOf, interpolate, messageOf, type DeepPartial } from "./utils"

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

export function UserAvatar({
  user,
  src = "",
  size = 48,
  token = "",
  client,
  fallbackSrc = "",
  genderFallbacks,
  alt = "",
  className = "",
  style,
}: {
  user?: AccountUser | null
  src?: string
  size?: number
  token?: string
  client?: AccountClient | null
  fallbackSrc?: string
  genderFallbacks?: GenderFallbacks | null
  alt?: string
  className?: string
  style?: CSSProperties
}) {
  ensureAccountStyle()
  const [blobUrl, setBlobUrl] = useState("")
  const blobRef = useRef("")

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (blobRef.current) {
        URL.revokeObjectURL(blobRef.current)
        blobRef.current = ""
        if (!cancelled) setBlobUrl("")
      }
      if (src) return
      const userId = user?.id
      if (!user?.has_custom_avatar || !client || !token || !userId) return
      try {
        const blob = await client.avatarBlob(userId, token)
        if (cancelled) return
        const url = URL.createObjectURL(blob)
        blobRef.current = url
        setBlobUrl(url)
      } catch {
        if (!cancelled) setBlobUrl("")
      }
    }
    void load()
    return () => {
      cancelled = true
      if (blobRef.current) {
        URL.revokeObjectURL(blobRef.current)
        blobRef.current = ""
      }
    }
  }, [src, user?.id, user?.has_custom_avatar, token, client])

  const fallback = fallbackSrcOf(user, genderFallbacks, fallbackSrc)
  const image = src || blobUrl || fallback
  const label = alt || user?.full_name || user?.username || "avatar"

  return (
    <span
      className={["ak-avatar", className].filter(Boolean).join(" ")}
      style={{ width: size, height: size, fontSize: Math.max(12, size / 2.4), ...style }}
      title={label}
    >
      {image ? <img src={image} alt={label} /> : initialsOf(user)}
    </span>
  )
}

export function AvatarUploader({
  client,
  token,
  user,
  language,
  labels,
  size = 72,
  accept = "image/jpeg,image/png,image/webp",
  fallbackSrc,
  genderFallbacks,
  className = "",
  prepareFile,
  onUploaded,
  onDeleted,
  onError,
  avatar,
}: {
  client: AccountClient
  token: string
  user?: AccountUser | null
  language?: string
  labels?: DeepPartial<ProfileLabels> | null
  size?: number
  accept?: string
  fallbackSrc?: string
  genderFallbacks?: GenderFallbacks | null
  className?: string
  prepareFile?: (file: File) => Promise<Blob | File> | Blob | File
  onUploaded?: (user: AccountUser) => void
  onDeleted?: (user: AccountUser) => void
  onError?: (error: unknown) => void
  avatar?: (ctx: { user: AccountUser | null; busy: boolean }) => ReactNode
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const L = useMemo(() => resolveProfileLabels(locale, labels), [locale, labels])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [current, setCurrent] = useState<AccountUser | null>(user || null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setCurrent(user || null)
  }, [user])

  async function upload(file: File) {
    setBusy(true)
    setError("")
    try {
      const prepared = prepareFile ? await prepareFile(file) : file
      const next = await client.uploadAvatar(token, prepared, file.name)
      setCurrent(next)
      onUploaded?.(next)
    } catch (e) {
      setError(messageOf(e, L.error))
      onError?.(e)
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError("")
    try {
      const next = await client.deleteAvatar(token)
      setCurrent(next)
      onDeleted?.(next)
    } catch (e) {
      setError(messageOf(e, L.error))
      onError?.(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={["ak-avatar-uploader", className].filter(Boolean).join(" ")}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ""
          if (file) void upload(file)
        }}
      />
      <button type="button" className="ak-avatar-btn" disabled={busy} title={L.uploadAvatar} onClick={() => inputRef.current?.click()}>
        {avatar?.({ user: current, busy }) || (
          <UserAvatar user={current} client={client} token={token} size={size} fallbackSrc={fallbackSrc} genderFallbacks={genderFallbacks} />
        )}
      </button>
      <div>
        <p className="ak-muted">{busy ? L.uploading : L.avatarHint}</p>
        {current?.has_custom_avatar ? (
          <button type="button" className="ak-btn ak-btn-outline ak-btn-small" disabled={busy} onClick={() => void remove()}>
            {L.deleteAvatar}
          </button>
        ) : null}
        {error ? <p className="ak-error">{error}</p> : null}
      </div>
    </div>
  )
}

export function ProfileFields({
  client,
  token,
  user,
  language,
  labels,
  showChangePassword = true,
  passwordEmailCode = "auto",
  className = "",
  extra,
  onSaved,
  onPasswordChanged,
}: {
  client: AccountClient
  token: string
  user?: AccountUser | null
  language?: string
  labels?: DeepPartial<ProfileLabels> | null
  showChangePassword?: boolean
  /**
   * Email code for password changes (server ``change_password_require_email_code``):
   * ``true`` always shows the code field, ``"auto"`` (default) shows it once the server
   * answers ``EMAIL_CODE_REQUIRED``, ``false`` never.
   */
  passwordEmailCode?: boolean | "auto"
  className?: string
  extra?: ReactNode
  onSaved?: (result: ProfileUpdateResult) => void
  onPasswordChanged?: () => void
}) {
  ensureAccountStyle()
  const locale = useKitLocale(language)
  const L = useMemo(() => resolveProfileLabels(locale, labels), [locale, labels])
  const [fullName, setFullName] = useState(user?.full_name || "")
  const [institution, setInstitution] = useState(user?.institution || "")
  const [gender, setGender] = useState(user?.gender || "")
  const [birth, setBirth] = useState(user?.birth_year_month || "")
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [emailCode, setEmailCode] = useState("")
  const [codeNeeded, setCodeNeeded] = useState(false)
  const [sending, setSending] = useState(false)
  const [cooldown, startCooldown] = useCountdown()
  const [error, setError] = useState("")
  const [info, setInfo] = useState("")
  const [busy, setBusy] = useState(false)
  const showCode = passwordEmailCode === true || (passwordEmailCode === "auto" && codeNeeded)

  async function sendPasswordCode() {
    const email = user?.email
    if (!email) return
    setError("")
    setSending(true)
    try {
      await client.sendCode(email, "change_password", locale, token)
      setInfo(interpolate(L.codeSentTo, { email }))
      startCooldown(60)
    } catch (e) {
      setError(messageOf(e, L.error))
    } finally {
      setSending(false)
    }
  }

  useEffect(() => {
    setFullName(user?.full_name || "")
    setInstitution(user?.institution || "")
    setGender(user?.gender || "")
    setBirth(user?.birth_year_month || "")
  }, [user])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError("")
    setInfo("")
    if (newPassword && newPassword !== confirmPassword) {
      setError(L.passwordMismatch)
      return
    }
    setBusy(true)
    try {
      const patched = await client.patchMe(token, {
        full_name: fullName.trim() || null,
        institution: institution.trim() || null,
        gender: gender || null,
        birth_year_month: birth || null,
      })
      onSaved?.(patched)
      if (newPassword) {
        try {
          await client.changePassword(token, oldPassword, newPassword, emailCode.trim() || undefined)
        } catch (e) {
          if (errorCodeOf(e) === "EMAIL_CODE_REQUIRED" && passwordEmailCode !== false) {
            setCodeNeeded(true)
            setError(L.passwordEmailCodeHint)
            return
          }
          throw e
        }
        setOldPassword("")
        setNewPassword("")
        setConfirmPassword("")
        setEmailCode("")
        onPasswordChanged?.()
        setInfo(L.passwordChanged)
      } else {
        setInfo(L.saved)
      }
    } catch (e) {
      setError(messageOf(e, L.error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className={["ak-form", className].filter(Boolean).join(" ")} onSubmit={submit}>
      <label>
        {L.fullName}
        <input value={fullName} autoComplete="name" onChange={(event) => setFullName(event.target.value)} />
      </label>
      <label>
        {L.institution}
        <input value={institution} onChange={(event) => setInstitution(event.target.value)} />
      </label>
      <label>
        {L.gender}
        <select value={gender} onChange={(event) => setGender(event.target.value)}>
          <option value="">{L.genderUnspecified}</option>
          <option value="male">{L.genderMale}</option>
          <option value="female">{L.genderFemale}</option>
        </select>
      </label>
      <label>
        {L.birth}
        <input type="month" value={birth} onChange={(event) => setBirth(event.target.value)} />
      </label>
      {showChangePassword ? (
        <>
          <h3 style={{ margin: "8px 0 0", fontSize: 15 }}>{L.changePassword}</h3>
          <label>
            {L.oldPassword}
            <input type="password" value={oldPassword} autoComplete="current-password" onChange={(event) => setOldPassword(event.target.value)} />
          </label>
          <label>
            {L.newPassword}
            <input type="password" value={newPassword} autoComplete="new-password" onChange={(event) => setNewPassword(event.target.value)} />
          </label>
          <label>
            {L.confirmPassword}
            <input type="password" value={confirmPassword} autoComplete="new-password" onChange={(event) => setConfirmPassword(event.target.value)} />
          </label>
          {showCode ? (
            <label>
              {L.emailCode}
              <span className="ak-row">
                <input
                  className="ak-input"
                  value={emailCode}
                  maxLength={6}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder={L.emailCodePlaceholder}
                  onChange={(event) => setEmailCode(event.target.value)}
                />
                <button type="button" disabled={sending || cooldown > 0 || !user?.email} onClick={() => void sendPasswordCode()}>
                  {sending ? L.sending : cooldown > 0 ? interpolate(L.resendIn, { s: cooldown }) : L.sendCode}
                </button>
              </span>
            </label>
          ) : null}
        </>
      ) : null}
      {extra}
      {error ? <p className="ak-error">{error}</p> : null}
      {info ? <p className="ak-success">{info}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? L.saving : L.save}
      </button>
    </form>
  )
}
