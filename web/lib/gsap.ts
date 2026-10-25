"use client"

import { gsap } from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import { useGSAP } from "@gsap/react"

gsap.registerPlugin(ScrollTrigger, useGSAP)

/** Matches --ease-out-strong: cubic-bezier(0.23, 1, 0.32, 1). */
export const EASE_OUT = "expo.out"

export const MOTION_OK = "(prefers-reduced-motion: no-preference)"

export { gsap, ScrollTrigger, useGSAP }
