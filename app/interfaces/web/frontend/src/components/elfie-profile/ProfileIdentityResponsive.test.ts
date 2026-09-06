import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const profileStyles = readFileSync(resolve(import.meta.dirname, "../../shared/chat-profile.css"), "utf8")

describe("profile identity responsive rules", () => {
  it("switches metadata to one column when the identity copy is narrow", () => {
    expect(profileStyles).toMatch(
      /\.profile-dossier__identity-copy\s*\{[^}]*container-type: inline-size;/,
    )
    expect(profileStyles).toMatch(
      /@container \(max-width: 560px\)[\s\S]*\.profile-dossier__metadata\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/,
    )
  })

  it("colors the gender character without drawing a badge", () => {
    const genderRule = profileStyles.match(
      /\.profile-dossier__attributes \.profile-dossier__gender\s*\{[^}]+\}/,
    )?.[0] ?? ""
    expect(genderRule).not.toContain("border: 2px")
    expect(genderRule).not.toContain("border-radius: 50%")
    expect(genderRule).toContain("font-size: 22px !important;")
    expect(profileStyles).toContain(".profile-dossier__gender--male { color: #2f70a8;")
    expect(profileStyles).toContain(".profile-dossier__gender--female { color: #bd5d7b;")
  })

  it("floats the chat action when the dossier container is narrow", () => {
    expect(profileStyles).toMatch(
      /@container \(max-width: 720px\)[\s\S]*?\.profile-dossier__identity\s*\{[^}]*grid-template-areas: "portrait identity";/,
    )
    expect(profileStyles).toMatch(
      /@container \(max-width: 720px\)[\s\S]*?\.profile-dossier__chat\s*\{[^}]*position: absolute;[^}]*top:/,
    )
  })
})
