import Link from "next/link"
import { cn } from "cn"

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      className={cn("size-7 shrink-0", className)}
    >
      <rect width="32" height="32" rx="9" fill="#00D393" />
      <rect x="8" y="9" width="16" height="3" rx="1.5" fill="#0A0A0A" />
      <rect x="8" y="14.5" width="16" height="3" rx="1.5" fill="#0A0A0A" />
      <rect x="8" y="20" width="9" height="3" rx="1.5" fill="#0A0A0A" />
    </svg>
  )
}

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      aria-label="Ledger home"
      className={cn(
        "inline-flex items-center gap-2 rounded-lg text-[1.0625rem] font-semibold tracking-tight outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        className
      )}
    >
      <LogoMark />
      Ledger
    </Link>
  )
}
