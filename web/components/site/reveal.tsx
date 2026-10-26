"use client"

import { useRef } from "react"
import { EASE_OUT, MOTION_OK, gsap, useGSAP } from "@/lib/gsap"

/**
 * Fades and lifts every `[data-reveal]` descendant into view once, staggered,
 * when the wrapper scrolls into the viewport. Reduced-motion users get the
 * content immediately.
 */
export function Reveal({
  children,
  className,
  stagger = 0.06,
  start = "top 85%",
}: {
  children: React.ReactNode
  className?: string
  stagger?: number
  start?: string
}) {
  const ref = useRef<HTMLDivElement>(null)

  useGSAP(
    () => {
      const mm = gsap.matchMedia()
      mm.add(MOTION_OK, () => {
        gsap.fromTo(
          "[data-reveal]",
          { autoAlpha: 0, y: 16 },
          {
            autoAlpha: 1,
            y: 0,
            duration: 0.7,
            ease: EASE_OUT,
            stagger,
            scrollTrigger: { trigger: ref.current, start, once: true },
          }
        )
      })
    },
    { scope: ref }
  )

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  )
}
