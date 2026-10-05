export type RenderQr = (otpauthUri: string) => Promise<string> | string

export async function renderQrDataUrl(otpauthUri: string, renderQr?: RenderQr | null): Promise<string> {
  if (renderQr) return await renderQr(otpauthUri)
  try {
    const mod = await import("qrcode")
    const toDataURL = mod.toDataURL ?? mod.default?.toDataURL
    if (typeof toDataURL !== "function") return ""
    return await toDataURL(otpauthUri, { width: 200, margin: 1 })
  } catch {
    return ""
  }
}
