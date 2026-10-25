/** USD, with enough precision that sub-cent LLM costs don't round to $0.00. */
export function formatCost(value: number) {
  if (value === 0) return "$0.00"
  const abs = Math.abs(value)
  if (abs >= 1) return `$${value.toFixed(2)}`
  if (abs >= 0.01) return `$${value.toFixed(4)}`
  // toPrecision switches to exponent notation below 1e-6.
  if (abs < 0.000001) return "<$0.000001"
  return `$${value.toPrecision(2)}`
}

/** Evaluation scores are 0–100. */
export function formatScore(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(1)
}

export function formatPercent(part: number, whole: number) {
  return whole === 0 ? "—" : `${Math.round((part / whole) * 100)}%`
}

export function shortId(id: string) {
  return id.length > 8 ? id.slice(0, 8) : id
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}
