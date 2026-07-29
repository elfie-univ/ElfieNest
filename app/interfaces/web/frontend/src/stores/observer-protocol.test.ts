import { describe, expect, it } from "vitest"

import { parseObserverCameraCatalog, parseObserverCameraCommand } from "./observer-protocol"

function validCatalog() {
  return {
    channel: "elfienest.observer",
    version: 1,
    kind: "camera_catalog",
    revision: 2,
    views: [
      { id: "overview", label: "总览" },
      { id: "dorm-01", label: "宿舍区" },
    ],
    active_id: "overview",
    presentation_paused: false,
  }
}

describe("observer camera protocol", () => {
  it("parses only JSON catalog envelopes", () => {
    expect(parseObserverCameraCatalog(validCatalog())).toBeNull()
    expect(parseObserverCameraCatalog(JSON.stringify(validCatalog()))).toMatchObject({
      revision: 2,
      activeId: "overview",
    })
  })

  it("rejects malformed JSON catalog payloads", () => {
    const malformedPayload = "{\"channel\":"

    expect(parseObserverCameraCatalog(malformedPayload)).toBeNull()
  })

  it("requires a version in JSON catalog envelopes", () => {
    const payloadWithoutVersion = JSON.stringify({
      ...validCatalog(),
      version: undefined,
    })

    expect(parseObserverCameraCatalog(payloadWithoutVersion)).toBeNull()
  })

  it("rejects coordinate-bearing top-level catalog fields", () => {
    const payload = JSON.stringify({
      ...validCatalog(),
      camera_position: { x: 1, y: 2, z: 3 },
    })

    expect(parseObserverCameraCatalog(payload)).toBeNull()
  })

  it("rejects coordinate-bearing nested camera view fields", () => {
    const payload = JSON.stringify({
      ...validCatalog(),
      views: [
        { id: "overview", label: "总览", x: 1 },
        { id: "dorm-01", label: "宿舍区" },
      ],
    })

    expect(parseObserverCameraCatalog(payload)).toBeNull()
  })

  it("rejects duplicate, empty, inactive, and nonpositive catalog revisions", () => {
    const duplicateIds = JSON.stringify({
      ...validCatalog(),
      views: [{ id: "overview", label: "总览" }, { id: "overview", label: "第二总览" }],
    })
    const inactiveId = JSON.stringify({ ...validCatalog(), active_id: "missing" })
    const emptyViews = JSON.stringify({ ...validCatalog(), views: [] })
    const revisionZero = JSON.stringify({ ...validCatalog(), revision: 0 })
    const negativeRevision = JSON.stringify({ ...validCatalog(), revision: -1 })

    expect(parseObserverCameraCatalog(duplicateIds)).toBeNull()
    expect(parseObserverCameraCatalog(inactiveId)).toBeNull()
    expect(parseObserverCameraCatalog(emptyViews)).toBeNull()
    expect(parseObserverCameraCatalog(revisionZero)).toBeNull()
    expect(parseObserverCameraCatalog(negativeRevision)).toBeNull()
  })

  it("accepts only exact high-level camera commands", () => {
    expect(parseObserverCameraCommand({
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_command",
      action: "select",
      view_id: "dorm-01",
    })).toMatchObject({ action: "select", view_id: "dorm-01" })
    expect(parseObserverCameraCommand({
      channel: "elfienest.observer",
      version: 1,
      kind: "camera_command",
      action: "overview",
      camera_position: { x: 1, y: 2, z: 3 },
    })).toBeNull()
  })
})
