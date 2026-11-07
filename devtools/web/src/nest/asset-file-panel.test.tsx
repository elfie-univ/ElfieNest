import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AssetFilePanel, type AssetFile } from "./AssetFilePanel";

const chair: AssetFile = {
  title: "客厅专用部件",
  file: "furniture/sets/main-floor-1/central-living-local.glb",
  kind: "source",
  preview: "chair",
  size: { fileBytes: 65536, referenceBytes: 1024 },
  components: [{
    id: "barrel", title: "桶形单椅", count: 2, paths: ["left", "right"],
    size: { meshBytes: 2048, textureBytes: 1024, instances: 2 },
  }],
};
const room: AssetFile = {
  title: "客厅",
  file: "furniture/sets/main-floor-1/central-living.scn",
  kind: "assembly",
  preview: "room",
  size: { fileBytes: 2048, referenceBytes: 66560 },
  parts: [{
    id: "chair", component: "barrel", title: "桶形单椅", count: 2, unit: "实例",
    paths: ["left", "right"], targetPaths: ["left", "right"],
  }],
};
const props = {
  entries: { chair, room },
  openFile: () => {},
  inspect: () => {},
  selectedPart: "barrel",
  back: undefined,
  busy: false,
};

describe("asset file inspector", () => {
  it("shows GLB subparts with mesh bytes and placement counts", () => {
    const html = renderToStaticMarkup(<AssetFilePanel {...props} entry={chair} />);
    expect(html).toContain("<h3>子部件</h3>");
    expect(html).toContain("总大小");
    expect(html).toContain("65.0 KiB");
    expect(html).toContain("外置贴图 1.0 KiB");
    expect(html).toContain("桶形单椅");
    expect(html).toContain("2.0 KiB");
    expect(html).toContain("2 个");
    expect(html).not.toContain("3.0 KiB");
    expect(html).not.toContain("份网格");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain(`>${chair.file}</small>`);
  });

  it("shows the referenced subpart size and separates the SCN file from its dependencies", () => {
    const root = "res://nest/";
    const html = renderToStaticMarkup(<AssetFilePanel {...props} entry={room} root={root} />);
    expect(html).toContain("<h3>引用</h3>");
    expect(html).toContain("桶形单椅");
    expect(html).toContain("×2");
    expect(html).toContain("67.0 KiB");
    expect(html).toContain("文件 2.0 KiB · 引用 65.0 KiB");
    expect(html).toContain("3.0 KiB");
    expect(html).toContain('aria-label="高亮桶形单椅"');
    expect(html).not.toContain("<h3>子部件</h3>");
    expect(html).toContain(`>${root}${room.file}</small>`);
    expect(html).toContain(`title="${root}${chair.file}"`);
    expect(html).toContain(">central-living-local.glb</small>");
  });
});
