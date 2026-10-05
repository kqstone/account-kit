import { ensureAccountStyle } from "./client"

export function TierBadge({ name, color = "#8c8c8c" }: { name: string; color?: string | null }) {
  ensureAccountStyle()
  return (
    <span className="ak-badge" style={{ background: color || "#8c8c8c" }}>
      {name}
    </span>
  )
}
