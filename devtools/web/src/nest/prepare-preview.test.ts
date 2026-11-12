import {afterEach, describe, expect, it, vi} from "vitest";
import {prepareNestPreview} from "./prepare-preview";

afterEach(() => vi.unstubAllGlobals());

describe("preview preparation", () => {
  it("waits for the shared preparation before allowing a renderer to load", async () => {
    let finish!: (response: Response) => void;
    const fetch = vi.fn(() => new Promise<Response>(resolve => { finish = resolve; }));
    vi.stubGlobal("fetch", fetch);
    let loaded = false;
    const preparing = prepareNestPreview().then(() => { loaded = true; });
    await Promise.resolve();
    expect(loaded).toBe(false);
    expect(fetch.mock.calls[0]).toEqual(["/api/preview/prepare",{method:"POST",signal:null}]);
    finish(new Response(JSON.stringify({ready:true})));
    await preparing;
    expect(loaded).toBe(true);
  });
  it("rejects failed preparation so the caller does not load a partial bundle", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("",{status:503})));
    await expect(prepareNestPreview()).rejects.toThrow("预览更新失败");
  });
});
