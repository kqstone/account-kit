import { mergeLabels, resolveLocale, type DeepPartial } from "./utils"

export type TwoFactorLabels = {
  title: string
  description: string
  statusOn: string
  statusOff: string
  enable: string
  disable: string
  regenerate: string
  next: string
  done: string
  verify: string
  verifying: string
  copy: string
  copied: string
  download: string
  currentPassword: string
  enterCode: string
  recoveryCode: string
  scanStep1: string
  scanStep2: string
  manualEntry: string
  recoveryTitle: string
  recoveryHint: string
  recoverySavedAck: string
  recoveryRemaining: string
  enabledOk: string
  disabledOk: string
  disableTitle: string
  regenerateTitle: string
  disableHint: string
  skipDisable: string
  emailCode: string
  emailCodePlaceholder: string
  sendEmailCode: string
  resendIn: string
  emailSentTo: string
  trustedDevices: string
  trustedDevicesHint: string
  noTrustedDevices: string
  revoke: string
  revokeAll: string
  lastUsed: string
  expires: string
  loading: string
  cancel: string
  error: string
  qrUnavailable: string
  login: {
    title: string
    hint: string
    recoveryHint: string
    trustDevice: string
    useRecovery: string
    useApp: string
    emailTitle: string
    emailHint: string
    skip: string
    alreadyLoggedInTitle: string
    alreadyLoggedInBody: string
    unsavedDataWarning: string
    forceLoginConfirm: string
    forceLoginCancel: string
    unknownDevice: string
  }
  errors: Record<string, string>
}

export type ProfileLabels = {
  fullName: string
  institution: string
  gender: string
  genderMale: string
  genderFemale: string
  genderUnspecified: string
  birth: string
  save: string
  saving: string
  saved: string
  changePassword: string
  oldPassword: string
  newPassword: string
  confirmPassword: string
  passwordMismatch: string
  passwordChanged: string
  uploadAvatar: string
  deleteAvatar: string
  uploading: string
  avatarHint: string
  error: string
}

const twoFactorZh: TwoFactorLabels = {
  title: "两步验证（2FA）",
  description: "开启后，登录时除密码外还需输入验证器 App（如 Google Authenticator）生成的 6 位动态码。",
  statusOn: "已开启",
  statusOff: "未开启",
  enable: "启用两步验证",
  disable: "关闭两步验证",
  regenerate: "重新生成恢复码",
  next: "下一步",
  done: "完成",
  verify: "验证",
  verifying: "验证中…",
  copy: "复制",
  copied: "已复制到剪贴板",
  download: "下载 .txt",
  currentPassword: "当前密码",
  enterCode: "验证器中的 6 位验证码",
  recoveryCode: "恢复码",
  scanStep1: "在手机上打开验证器 App，扫描下方二维码（或手动输入密钥）。",
  scanStep2: "输入 App 显示的 6 位验证码完成绑定。",
  manualEntry: "无法扫码？手动输入密钥：",
  recoveryTitle: "请保存恢复码",
  recoveryHint: "手机丢失或无法使用验证器时，可用恢复码登录。每个恢复码只能使用一次，且仅显示这一次，请妥善保存。",
  recoverySavedAck: "我已妥善保存这些恢复码",
  recoveryRemaining: "剩余可用恢复码：{n} 个",
  enabledOk: "两步验证已开启",
  disabledOk: "两步验证已关闭",
  disableTitle: "关闭两步验证",
  regenerateTitle: "重新生成恢复码（旧恢复码将全部失效）",
  disableHint: "关闭需要验证当前密码，并输入验证器验证码或恢复码；无法使用验证器时可选择“跳过 2FA”，改用邮箱验证码。关闭后所有受信设备与恢复码将一并失效。",
  skipDisable: "跳过 2FA（改用邮箱验证码）",
  emailCode: "邮箱验证码",
  emailCodePlaceholder: "6 位邮箱验证码",
  sendEmailCode: "发送验证码",
  resendIn: "{s} 秒后重发",
  emailSentTo: "验证码已发送至 {email}",
  trustedDevices: "受信设备",
  trustedDevicesHint: "勾选“这是我的私人设备”登录后，该设备 {days} 天内无需再输入验证码。修改密码或关闭两步验证会使所有受信设备失效。",
  noTrustedDevices: "暂无受信设备",
  revoke: "移除",
  revokeAll: "全部移除",
  lastUsed: "最近使用",
  expires: "到期",
  loading: "加载中…",
  cancel: "取消",
  error: "请求失败",
  qrUnavailable: "未能生成二维码，请使用下方密钥手动添加。可安装 qrcode 或传入 renderQr。",
  login: {
    title: "两步验证",
    hint: "请输入验证器 App 中显示的 6 位验证码。",
    recoveryHint: "请输入一个未使用过的恢复码（格式 xxxx-xxxx）。",
    trustDevice: "这是我的私人设备（{days} 天内免验证）",
    useRecovery: "使用恢复码",
    useApp: "使用验证器验证码",
    emailTitle: "邮箱验证码登录",
    emailHint: "验证码已发送到账号绑定的邮箱，输入后即可登录。两步验证仍保持开启。",
    skip: "跳过 2FA（发送邮箱验证码登录）",
    alreadyLoggedInTitle: "已在其他设备登录",
    alreadyLoggedInBody: "该账号已在设备「{device}」登录。强制登录将注销其他端。",
    unsavedDataWarning: "其他端未保存的数据可能丢失。",
    forceLoginConfirm: "强制登录",
    forceLoginCancel: "取消",
    unknownDevice: "未知设备",
  },
  errors: {
    PASSWORD_INCORRECT: "密码错误",
    MFA_CODE_REQUIRED: "请输入验证码",
    MFA_CODE_INVALID: "验证码错误，请重试",
    MFA_CHALLENGE_INVALID: "登录验证已过期，请重新输入密码登录",
    MFA_TOO_MANY_ATTEMPTS: "验证码错误次数过多，请重新登录",
    MFA_ALREADY_VERIFIED: "已完成验证，请继续登录",
    RATE_LIMITED: "尝试次数过多，请稍后再试",
    TWO_FACTOR_ALREADY_ENABLED: "两步验证已开启",
    TWO_FACTOR_NOT_ENABLED: "两步验证未开启",
    TWO_FACTOR_SETUP_REQUIRED: "请先生成二维码",
    TWO_FACTOR_SETUP_EXPIRED: "二维码已过期，请重新开始",
    TWO_FACTOR_CODE_INVALID: "验证码错误，请确认手机时间准确后重试",
    EMAIL_UNAVAILABLE: "账号未绑定邮箱",
    EMAIL_CODE_INVALID: "邮箱验证码错误或已失效",
    EMAIL_CODE_TOO_FREQUENT: "验证码发送过于频繁，请稍后再试",
    DEVICE_NOT_FOUND: "设备不存在或已移除",
  },
}

const twoFactorEn: TwoFactorLabels = {
  title: "Two-step verification (2FA)",
  description: "When on, signing in requires a 6-digit code from an authenticator app in addition to your password.",
  statusOn: "On",
  statusOff: "Off",
  enable: "Turn on 2FA",
  disable: "Turn off 2FA",
  regenerate: "Regenerate recovery codes",
  next: "Next",
  done: "Done",
  verify: "Verify",
  verifying: "Verifying…",
  copy: "Copy",
  copied: "Copied to clipboard",
  download: "Download .txt",
  currentPassword: "Current password",
  enterCode: "6-digit code from your authenticator",
  recoveryCode: "Recovery code",
  scanStep1: "Open your authenticator app and scan the QR code below (or enter the key manually).",
  scanStep2: "Enter the 6-digit code shown in the app to finish.",
  manualEntry: "Can't scan? Enter this key:",
  recoveryTitle: "Save your recovery codes",
  recoveryHint: "If you lose your phone, use a recovery code to sign in. Each code works once and is shown only now. Keep them safe.",
  recoverySavedAck: "I have saved these recovery codes",
  recoveryRemaining: "Recovery codes left: {n}",
  enabledOk: "Two-step verification is on",
  disabledOk: "Two-step verification is off",
  disableTitle: "Turn off two-step verification",
  regenerateTitle: "Regenerate recovery codes (old codes stop working)",
  disableHint: "Turning off requires your current password plus an authenticator or recovery code. If you can't use your authenticator, choose “Skip 2FA” to use an email code instead. All trusted devices and recovery codes will be removed.",
  skipDisable: "Skip 2FA (use an email code)",
  emailCode: "Email code",
  emailCodePlaceholder: "6-digit email code",
  sendEmailCode: "Send code",
  resendIn: "Resend in {s}s",
  emailSentTo: "Code sent to {email}",
  trustedDevices: "Trusted devices",
  trustedDevicesHint: "Devices signed in with “This is my private device” skip the code for {days} days. Changing your password or turning off 2FA removes all trusted devices.",
  noTrustedDevices: "No trusted devices",
  revoke: "Remove",
  revokeAll: "Remove all",
  lastUsed: "Last used",
  expires: "Expires",
  loading: "Loading…",
  cancel: "Cancel",
  error: "Request failed",
  qrUnavailable: "Could not render a QR code. Enter the key below, or pass renderQr / install the qrcode peer.",
  login: {
    title: "Two-step verification",
    hint: "Enter the 6-digit code from your authenticator app.",
    recoveryHint: "Enter an unused recovery code (xxxx-xxxx).",
    trustDevice: "This is my private device (skip for {days} days)",
    useRecovery: "Use a recovery code",
    useApp: "Use authenticator code",
    emailTitle: "Sign in with an email code",
    emailHint: "We sent a code to your account email. Enter it to sign in. Two-step verification stays on.",
    skip: "Skip 2FA (sign in with an email code)",
    alreadyLoggedInTitle: "Already signed in elsewhere",
    alreadyLoggedInBody: "This account is signed in on “{device}”. Force login will sign out the other session.",
    unsavedDataWarning: "Unsaved data on the other device may be lost.",
    forceLoginConfirm: "Force login",
    forceLoginCancel: "Cancel",
    unknownDevice: "unknown device",
  },
  errors: {
    PASSWORD_INCORRECT: "Incorrect password",
    MFA_CODE_REQUIRED: "Please enter the code",
    MFA_CODE_INVALID: "Incorrect code, please try again",
    MFA_CHALLENGE_INVALID: "Verification expired. Please sign in again",
    MFA_TOO_MANY_ATTEMPTS: "Too many wrong codes. Please sign in again",
    MFA_ALREADY_VERIFIED: "Already verified, please continue",
    RATE_LIMITED: "Too many attempts. Please try again later",
    TWO_FACTOR_ALREADY_ENABLED: "Two-step verification is already on",
    TWO_FACTOR_NOT_ENABLED: "Two-step verification is not on",
    TWO_FACTOR_SETUP_REQUIRED: "Please generate the QR code first",
    TWO_FACTOR_SETUP_EXPIRED: "QR code expired, please start again",
    TWO_FACTOR_CODE_INVALID: "Incorrect code. Check that your phone's time is correct",
    EMAIL_UNAVAILABLE: "No email on this account",
    EMAIL_CODE_INVALID: "Email code is wrong or expired",
    EMAIL_CODE_TOO_FREQUENT: "Codes sent too often, please wait",
    DEVICE_NOT_FOUND: "Device not found",
  },
}

const profileZh: ProfileLabels = {
  fullName: "姓名",
  institution: "机构",
  gender: "性别",
  genderMale: "男",
  genderFemale: "女",
  genderUnspecified: "未指定",
  birth: "出生年月",
  save: "保存",
  saving: "保存中…",
  saved: "已保存",
  changePassword: "修改密码",
  oldPassword: "当前密码",
  newPassword: "新密码",
  confirmPassword: "确认新密码",
  passwordMismatch: "两次输入的新密码不一致",
  passwordChanged: "密码已修改",
  uploadAvatar: "上传头像",
  deleteAvatar: "使用默认头像",
  uploading: "上传中…",
  avatarHint: "点击头像上传，支持 JPG / PNG / WEBP。未上传时按性别显示默认头像。",
  error: "请求失败",
}

const profileEn: ProfileLabels = {
  fullName: "Full name",
  institution: "Institution",
  gender: "Gender",
  genderMale: "Male",
  genderFemale: "Female",
  genderUnspecified: "Unspecified",
  birth: "Birth month",
  save: "Save",
  saving: "Saving…",
  saved: "Saved",
  changePassword: "Change password",
  oldPassword: "Current password",
  newPassword: "New password",
  confirmPassword: "Confirm new password",
  passwordMismatch: "New passwords do not match",
  passwordChanged: "Password updated",
  uploadAvatar: "Upload avatar",
  deleteAvatar: "Use default avatar",
  uploading: "Uploading…",
  avatarHint: "Click the avatar to upload JPG / PNG / WEBP. A gender fallback is used until you upload one.",
  error: "Request failed",
}

export const defaultTwoFactorLabels = { zh: twoFactorZh, en: twoFactorEn }
export const defaultProfileLabels = { zh: profileZh, en: profileEn }

export function resolveTwoFactorLabels(language?: string, override?: DeepPartial<TwoFactorLabels> | null): TwoFactorLabels {
  return mergeLabels(defaultTwoFactorLabels[resolveLocale(language)], override)
}

export function resolveProfileLabels(language?: string, override?: DeepPartial<ProfileLabels> | null): ProfileLabels {
  return mergeLabels(defaultProfileLabels[resolveLocale(language)], override)
}
