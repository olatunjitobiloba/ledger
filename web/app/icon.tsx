import { ImageResponse } from "next/og"
import { IconArt } from "@/lib/icon-art"

const icons = {
  "32": { size: 32, inset: 0 },
  "192": { size: 192, inset: 0 },
  "512": { size: 512, inset: 0 },
  maskable: { size: 512, inset: 0.2 },
} as const

export function generateImageMetadata() {
  return Object.entries(icons).map(([id, { size }]) => ({
    id,
    contentType: "image/png",
    size: { width: size, height: size },
  }))
}

export default async function Icon({ id }: { id: Promise<string | number> }) {
  const { size, inset } = icons[(await id) as keyof typeof icons]
  return new ImageResponse(<IconArt size={size} inset={inset} />, {
    width: size,
    height: size,
  })
}
