export { AccountApiError, createAccountClient, createTokenStore, ensureAccountStyle } from "./client"
export type {
  AccountClient,
  AccountClientOptions,
  AccountUser,
  CaptchaChallenge,
  CodePurpose,
  CodeSentResult,
  DeleteAccountPayload,
  LoginSecondFactorResult,
  ProfileUpdateResult,
  RoleChangeRequest,
  SecondFactorPayload,
  TokenPair,
  TokenStore,
  TrustedDevice,
  TwoFactorSetup,
  TwoFactorStatus,
} from "./client"
export { LoginForm, RegisterForm, ResetPasswordForm } from "./forms"
export { ACCOUNT_I18N_KEY, accountKitI18n, followVueI18n, provideAccountI18n, useAccountI18n, useKitLocale } from "./i18n"
export type { AccountI18nContext, AccountI18nSource, VueI18nLike } from "./i18n"
export { defaultErrorLabels } from "./errors"
export { errorCodeOf, formatDateTime, formatError, resolveLocale } from "./utils"
export type { KitLocale } from "./utils"
export {
  defaultFormLabels,
  defaultProfileLabels,
  defaultTwoFactorLabels,
  resolveFormLabels,
  resolveProfileLabels,
  resolveTwoFactorLabels,
} from "./labels"
export type { AccountLocaleMessages, AccountMessagesOverride, FormLabels, ProfileLabels, TwoFactorLabels } from "./labels"
export {
  canSubmitFactor,
  FACTOR_EMAIL,
  FACTOR_RECOVERY,
  FACTOR_TOTP,
  formatSecret,
  getMfaChallenge,
  normalizeChallenge,
  normalizeRecoveryInput,
  normalizeTotpInput,
  secondFactorFields,
} from "./mfa"
export type { MfaChallenge, SecondFactor } from "./mfa"
export { AvatarUploader, ProfileFields, UserAvatar } from "./profile"
export type { GenderFallbacks } from "./profile"
export type { RenderQr } from "./qr"
export { CaptchaImage, ChangeEmailForm, DeleteAccountForm, LogoutButton, splitSecondFactor } from "./security"
export { TierBadge } from "./TierBadge"
export {
  clearTrustedDeviceToken,
  clearTrustedDeviceTokensForUser,
  getTrustedDeviceToken,
  saveTrustedDeviceToken,
  TRUSTED_DEVICE_STORAGE_KEY,
  trustedDeviceScope,
} from "./trustedDevice"
export { TwoFactorLoginDialog, TwoFactorSettings } from "./twoFactor"
