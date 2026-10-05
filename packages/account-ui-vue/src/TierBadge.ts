import { defineComponent, h } from "vue"
import { ensureAccountStyle } from "./client"

export const TierBadge = defineComponent({
  name: "TierBadge",
  props: {
    name: { type: String, required: true },
    color: { type: String, default: "#8c8c8c" },
  },
  setup(props) {
    ensureAccountStyle()
    return () =>
      h(
        "span",
        { class: "ak-badge", style: { background: props.color || "#8c8c8c" } },
        props.name,
      )
  },
})
