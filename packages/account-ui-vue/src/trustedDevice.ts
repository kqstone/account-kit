const DEFAULT_KEY = "account-kit-trusted-devices-v1"

function storage() {
  try {
    return globalThis.localStorage || null
  } catch {
    return null
  }
}

export function trustedDeviceScope(serverUrl: string, username: string) {
  const server = String(serverUrl || "")
    .trim()
    .replace(/\/+$/, "")
    .toLowerCase()
  const user = String(username || "")
    .trim()
    .toLowerCase()
  return `${server}|${user}`
}

function readAll(storageKey = DEFAULT_KEY): Record<string, { token?: string; expiresAt?: string | null }> {
  const ls = storage()
  if (!ls) return {}
  try {
    const parsed = JSON.parse(ls.getItem(storageKey) || "{}")
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function writeAll(map: Record<string, unknown>, storageKey = DEFAULT_KEY) {
  const ls = storage()
  if (!ls) return
  if (!map || Object.keys(map).length === 0) ls.removeItem(storageKey)
  else ls.setItem(storageKey, JSON.stringify(map))
}

export function getTrustedDeviceToken(scope: string, storageKey = DEFAULT_KEY, now = Date.now()) {
  const all = readAll(storageKey)
  const entry = all[scope]
  if (!entry || typeof entry.token !== "string" || !entry.token) return ""
  const exp = entry.expiresAt ? Date.parse(entry.expiresAt) : NaN
  if (!Number.isNaN(exp) && exp <= now) {
    delete all[scope]
    writeAll(all, storageKey)
    return ""
  }
  return entry.token
}

export function saveTrustedDeviceToken(scope: string, token: string, expiresAt?: string | null, storageKey = DEFAULT_KEY) {
  if (!scope || !token) return
  const all = readAll(storageKey)
  let iso: string | null = null
  if (expiresAt) {
    const raw = String(expiresAt)
    iso = /[zZ]|[+-]\d\d:?\d\d$/.test(raw) ? raw : `${raw}Z`
  }
  all[scope] = { token, expiresAt: iso }
  writeAll(all, storageKey)
}

export function clearTrustedDeviceToken(scope: string, storageKey = DEFAULT_KEY) {
  const all = readAll(storageKey)
  if (scope in all) {
    delete all[scope]
    writeAll(all, storageKey)
  }
}

export function clearTrustedDeviceTokensForUser(username: string, storageKey = DEFAULT_KEY) {
  const user = String(username || "")
    .trim()
    .toLowerCase()
  if (!user) return
  const all = readAll(storageKey)
  let changed = false
  for (const key of Object.keys(all)) {
    if (key.endsWith(`|${user}`)) {
      delete all[key]
      changed = true
    }
  }
  if (changed) writeAll(all, storageKey)
}

export const TRUSTED_DEVICE_STORAGE_KEY = DEFAULT_KEY
