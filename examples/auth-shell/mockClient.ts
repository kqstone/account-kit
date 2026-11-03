// Offline mock client for the visual demo: every method resolves with an empty value.
export const mockClient: any = new Proxy(
  {},
  { get: (_t, key) => (key === "then" ? undefined : async () => (String(key).toLowerCase().includes("role") ? [] : {})) },
)
