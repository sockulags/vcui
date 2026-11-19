import { describe, expect, it } from "vitest"
import { isNoise, isUndo, yesOrNo } from "./speech"

describe("isNoise", () => {
  it("drops what Whisper writes on near-silence", () => {
    expect(isNoise("Tack för att ni tittade!")).toBe(true)
    expect(isNoise("Textning.nu")).toBe(true)
    expect(isNoise(" . ")).toBe(true)
  })

  it("keeps real commands", () => {
    expect(isNoise("Lägg till köp kaffe")).toBe(false)
    expect(isNoise("Visa musiklistan")).toBe(false)
  })
})

describe("yesOrNo", () => {
  it("reads spoken answers to a confirmation", () => {
    expect(yesOrNo("Ja.")).toBe(true)
    expect(yesOrNo("Ja tack!")).toBe(true)
    expect(yesOrNo("kör")).toBe(true)
    expect(yesOrNo("Nej")).toBe(false)
    expect(yesOrNo("Avbryt.")).toBe(false)
  })

  it("leaves other sentences to the agent", () => {
    expect(yesOrNo("Ja, och lägg till mjölk")).toBeNull()
    expect(yesOrNo("rensa alla klara")).toBeNull()
  })
})

describe("isUndo", () => {
  it("matches only a bare undo", () => {
    expect(isUndo("Ångra.")).toBe(true)
    expect(isUndo("ångra det")).toBe(true)
    expect(isUndo("ångra inte offerten")).toBe(false)
  })
})
