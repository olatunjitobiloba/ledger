import { cn } from "cn"

export function SectionHeading({
  title,
  description,
  className,
}: {
  title: React.ReactNode
  description?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn("mx-auto max-w-2xl text-center", className)}>
      <h2
        data-reveal
        className="text-3xl leading-[1.1] font-semibold tracking-[-0.03em] text-balance sm:text-5xl"
      >
        {title}
      </h2>
      {description && (
        <p
          data-reveal
          className="mt-4 text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg"
        >
          {description}
        </p>
      )}
    </div>
  )
}
