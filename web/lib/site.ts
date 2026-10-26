const repo = "https://github.com/olatunjitobiloba/ledger"

export const site = {
  name: "Ledger",
  title: "Ledger — Release evidence for LLM applications",
  description:
    "Ledger records cost and risk on every AI call without slowing it down, scores each model change against a versioned golden set, and blocks the releases that regress.",
  links: {
    repo,
    quickStart: `${repo}#api-and-sdk-quick-start`,
    apiContract: `${repo}/blob/main/docs/api-contract.md`,
    deployment: `${repo}/blob/main/docs/deployment.md`,
    limitations: `${repo}#limitations`,
  },
} as const

export const navItems = [
  { label: "Features", href: "#features" },
  { label: "Why Ledger", href: "#why-ledger" },
  { label: "FAQ", href: "#faq" },
] as const
