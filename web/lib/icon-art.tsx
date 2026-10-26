/**
 * The Ledger mark drawn with flexbox for `next/og` image generation. `inset` is
 * the share of the canvas left as padding, so maskable icons can keep their
 * artwork inside the safe zone.
 */
export function IconArt({ size, inset = 0 }: { size: number; inset?: number }) {
  const art = size * (1 - inset * 2)
  const bar = art * 0.094
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: inset ? "#00D393" : "transparent",
      }}
    >
      <div
        style={{
          width: art,
          height: art,
          borderRadius: inset ? 0 : art * 0.28,
          background: "#00D393",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: art * 0.078,
          paddingLeft: art * 0.25,
          paddingRight: art * 0.25,
        }}
      >
        <div style={{ height: bar, width: "100%", borderRadius: bar, background: "#0A0A0A" }} />
        <div style={{ height: bar, width: "100%", borderRadius: bar, background: "#0A0A0A" }} />
        <div style={{ height: bar, width: "56%", borderRadius: bar, background: "#0A0A0A" }} />
      </div>
    </div>
  )
}
