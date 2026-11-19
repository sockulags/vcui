/** Rules for what a transcript means before it reaches the agent. */

const normalize = (text: string) =>
  text
    .toLowerCase()
    .normalize("NFC")
    .replace(/[.,!?…"”“]/g, "")
    .replace(/\s+/g, " ")
    .trim()

// Whisper models write these on near-silence; they are never commands.
const HALLUCINATIONS = [
  "tack för att ni tittade",
  "tack för att du tittade",
  "textning",
  "undertexter",
  "svensktextning",
  "textat av",
  "musik",
]

export function isNoise(text: string): boolean {
  if (text.toLowerCase().includes("textning.nu")) return true
  const t = normalize(text)
  if (t.length < 2) return true
  return HALLUCINATIONS.some((h) => t === h || t.startsWith(`${h} `))
}

const YES = /^(ja|japp|jajamän|absolut|kör|gör det|okej|ok|visst|javisst|bekräfta|ja tack)( tack)?$/
const NO = /^(nej|nä|nej tack|avbryt|stopp|låt bli|vänta)$/

export function yesOrNo(text: string): boolean | null {
  const t = normalize(text)
  if (YES.test(t)) return true
  if (NO.test(t)) return false
  return null
}

export function isUndo(text: string): boolean {
  return /^(ångra|ångra det|ångra senaste|gör ogjort)$/.test(normalize(text))
}
