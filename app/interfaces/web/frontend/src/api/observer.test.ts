import { describe, expect, it, vi } from "vitest"

import { requestJson } from "./http"
import { nextObserverFrame, openObserverSession, warmObserverAssets } from "./observer"

const { kyGet } = vi.hoisted(() => ({ kyGet: vi.fn() }))

vi.mock("ky", () => ({ default: { get: kyGet } }))

vi.mock("./http", () => ({
  csrfHeaders: vi.fn().mockReturnValue({ "X-CSRF-Token": "csrf" }),
  requestJson: vi.fn(),
}))

describe("openObserverSession", () => {
  it("uses the sole versioned Observer resource", async () => {
    vi.mocked(requestJson).mockResolvedValue({ capability: "observer-capability" })

    await expect(
      openObserverSession({ kind: "room", room_id: "local-nest" }, "csrf"),
    ).resolves.toBe("observer-capability")

    expect(requestJson).toHaveBeenCalledWith(
      "/api/v1/observer/sessions",
      expect.objectContaining({ method: "POST" }),
    )
  })
})

describe("nextObserverFrame", () => {
  it("accepts the Python room snapshot shape with a null inactive Elfie field", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      protocol: 3,
      kind: "snapshot",
      generation: 1,
      sequence: 1,
      scope: { kind: "room", room_id: "local-nest", elfie_id: null },
      entities: {},
      entity_revisions: {},
    })

    await expect(nextObserverFrame("capability", null)).resolves.toMatchObject({
      kind: "snapshot",
      scope: { kind: "room", room_id: "local-nest", elfie_id: null },
    })
    expect(requestJson).toHaveBeenCalledWith(
      "/api/v1/observer/frames",
      expect.any(Object),
    )
  })

  it("accepts the Python Elfie snapshot shape with a null inactive room field", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      protocol: 3,
      kind: "snapshot",
      generation: 1,
      sequence: 1,
      scope: { kind: "elfie", elfie_id: "fox-1", room_id: null },
      entities: {},
      entity_revisions: {},
    })

    await expect(nextObserverFrame("capability", null)).resolves.toMatchObject({
      kind: "snapshot",
      scope: { kind: "elfie", elfie_id: "fox-1", room_id: null },
    })
  })

  it("rejects a non-null inactive sibling field", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      protocol: 3,
      kind: "snapshot",
      generation: 1,
      sequence: 1,
      scope: { kind: "room", room_id: "local-nest", elfie_id: "fox-1" },
      entities: {},
      entity_revisions: {},
    })

    await expect(nextObserverFrame("capability", null)).rejects.toThrow()
  })

  it("rejects unknown scope fields", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      protocol: 3,
      kind: "snapshot",
      generation: 1,
      sequence: 1,
      scope: { kind: "room", room_id: "local-nest", elfie_id: null, authority: true },
      entities: {},
      entity_revisions: {},
    })

    await expect(nextObserverFrame("capability", null)).rejects.toThrow()
  })

  it("accepts explicit nullable semantic fields instead of treating their clears as malformed", async () => {
    vi.mocked(requestJson).mockResolvedValue({
      protocol: 3,
      kind: "delta",
      generation: 1,
      sequence: 2,
      scope: { kind: "elfie", elfie_id: "fox-1" },
      entity_id: "fox-1",
      entity_revision: 2,
      patch: { zone_id: null, active_command_id: null },
    })

    await expect(nextObserverFrame("capability", { generation: 1, sequence: 1 })).resolves.toMatchObject({
      kind: "delta",
      patch: { zone_id: null, active_command_id: null },
    })
  })
})

describe("warmObserverAssets", () => {
  it("prefetches only manifest-declared JavaScript, Wasm, and PCK payloads", async () => {
    const arrayBuffer = vi.fn().mockResolvedValue(new ArrayBuffer(0))
    kyGet
      .mockReturnValueOnce({
        json: vi.fn().mockResolvedValue({
          files: {
            "elfienest.html": { sha256: "a".repeat(64) },
            "elfienest.js": { sha256: "b".repeat(64) },
            "elfienest.wasm": { sha256: "c".repeat(64) },
            "elfienest.pck": { sha256: "d".repeat(64) },
            "metadata.json": { sha256: "e".repeat(64) },
          },
        }),
      })
      .mockReturnValue({ arrayBuffer })

    await warmObserverAssets()

    expect(kyGet.mock.calls.map(([url]) => url)).toEqual([
      "/runtime/godot/build-manifest.json",
      "/runtime/godot/elfienest.js",
      "/runtime/godot/elfienest.wasm",
      "/runtime/godot/elfienest.pck",
    ])
    expect(arrayBuffer).toHaveBeenCalledTimes(3)
  })
})
