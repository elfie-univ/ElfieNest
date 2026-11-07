import { useEffect, useRef, useState } from "react";
import { assetLeaves, type AssetItem } from "./asset-catalog";
import { AssetBrowserToolbar } from "./AssetBrowserToolbar";
import { AssetFilePanel, type AssetFileGraph } from "./AssetFilePanel";
import { modeUrl } from "./preview-mode";

const CHANNEL = "nest-v044-review";
const REVIEW_URL = "/godot-web/nest-assets";

type Audit = {
  assets: Record<string, { geometry: number; sample_colors: number }>;
  failures: string[];
};

type Inspection = { file: string; part: string; paths: string[]; solo: boolean };

export function StaticAssetReview() {
  const frame = useRef<HTMLIFrameElement>(null);
  const reviewCount = useRef(0);
  const [packFailed, setPackFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [selected, select] = useState<AssetItem>();
  const [fileGraph, setFileGraph] = useState<AssetFileGraph>();
  const [fileTrail, setFileTrail] = useState<string[]>([]);
  const [inspection, setInspection] = useState<Inspection>();
  const [showFiles, setShowFiles] = useState(true);
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<Audit | null>(null);
  const [failedId, setFailedId] = useState<string | null>(null);
  const categories = fileGraph?.categories ?? [];
  const menuAssets = categories.flatMap(category => assetLeaves(category.children));
  const defaultFile = selected && (fileGraph?.entries[selected.id] ? selected.id : fileGraph?.defaults?.[selected.id]);
  const fileId = fileTrail.at(-1) ?? defaultFile;
  const file = fileId ? fileGraph?.entries[fileId] : undefined;
  const shownId = file?.preview ?? selected?.id;
  const selection = fileId ?? selected?.id;
  const focus = file?.focus;
  const inspected = inspection?.file === fileId ? inspection : undefined;
  const toolbarAsset = menuAssets.find(asset => asset.id === fileId)
    ?? menuAssets.find(asset => file && fileGraph?.entries[asset.id]?.file === file.file)
    ?? menuAssets.find(asset => asset.id === file?.preview)
    ?? selected;

  function send(type: string, fields: Record<string, unknown> = {}) {
    frame.current?.contentWindow?.postMessage({ channel: CHANNEL, type, ...fields }, window.location.origin);
  }

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(`${REVIEW_URL}.json`, { signal: controller.signal });
        if (!response.ok) throw new Error("Missing Nest asset manifest");
        const manifest: { assets?: number; fileGraph?: AssetFileGraph } = await response.json();
        const graph = manifest.fileGraph;
        const items = graph?.categories?.flatMap(category => assetLeaves(category.children)) ?? [];
        const count = Object.keys(graph?.entries ?? {}).length;
        if (graph?.root !== "res://nest/" || !count || count !== manifest.assets ||
            items.length !== count || new Set(items.map(item => item.id)).size !== count ||
            items.some(item => !Object.hasOwn(graph.entries, item.id))) {
          throw new Error("Invalid Nest asset manifest");
        }
        if (controller.signal.aborted) return;
        reviewCount.current = count;
        select(items.find(item => item.id === "source:chair") ?? items[0]!);
        setFileGraph(graph);
      } catch {
        if (!controller.signal.aborted) setPackFailed(true);
      }
    })();
    function receive(event: MessageEvent) {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow ||
          event.data?.channel !== CHANNEL) return;
      switch (event.data.kind) {
        case "ready": setReady(event.data.total === reviewCount.current); break;
        case "shown": setFailedId(null); break;
        case "error": setFailedId(event.data.id); break;
        case "progress": setProgress(event.data.done); break;
        case "audit": setResult(event.data as Audit); setProgress(null); break;
      }
    }
    window.addEventListener("message", receive);
    return () => { controller.abort(); window.removeEventListener("message", receive); };
  }, []);

  useEffect(() => {
    if (ready && shownId) send("show", {
      id: shownId, selection, focus: focus ?? [],
      inspect: inspected?.paths ?? [], solo: inspected?.solo ?? false,
    });
  }, [ready, shownId, selection, focus, inspected]);

  function selectAsset(asset: AssetItem) {
    select(asset);
    setFileTrail([]);
    setInspection(undefined);
  }

  function openFile(id: string, paths?: string[], component?: string) {
    setFileTrail(trail => {
      if (id === defaultFile) return [];
      const previous = trail.indexOf(id);
      return previous === -1 ? [...trail, id] : trail.slice(0, previous + 1);
    });
    setInspection(paths?.length ? { file: id, part: component ?? "", paths, solo: Boolean(component) } : undefined);
  }

  function inspect(part: string, paths: string[], solo = false) {
    if (!fileId) return;
    setInspection(previous => {
      if (!paths.length || (!solo && previous?.part === part && !previous.solo)) return undefined;
      return { file: fileId, part, paths, solo };
    });
  }

  function goBack() {
    setFileTrail(trail => trail.slice(0, -1));
    setInspection(undefined);
  }

  function audit() {
    setResult(null);
    setProgress(0);
    send("audit");
  }

  return <main className="nest-monitor nest-monitor-asset" aria-label="Nest Lab">
    <section className="nest-monitor-stage" aria-label="Nest 资产预览">
      {fileGraph
        ? <iframe ref={frame} src={`${REVIEW_URL}.html`} title="Nest 资产预览" onLoad={() => send("hello")} />
        : <div className="nest-monitor-placeholder">{packFailed ? "Nest 正式资产预览包未就绪" : "加载中…"}</div>}
      {failedId === selection && <div className="nest-monitor-placeholder" role="alert">预览加载失败</div>}
    </section>
    <div className="nest-pilot-modes" role="group" aria-label="预览模式">
      <button type="button" aria-pressed={false} onClick={() => window.location.assign(modeUrl(window.location.href, false))}>整体场景</button>
      <button type="button" aria-pressed={true}>单件资产</button>
    </div>
    {toolbarAsset && <AssetBrowserToolbar categories={categories} selected={toolbarAsset} select={selectAsset} reset={() => send("reset")} ready={ready} busy={progress !== null} />}
    <div className="nest-asset-audit">
      {file && <button type="button" aria-expanded={showFiles} onClick={() => setShowFiles(value => !value)}>文件与引用</button>}
      {result && <output aria-label="校验结果" data-report={JSON.stringify(result)} title={result.failures.map(id => fileGraph?.entries[id]?.title ?? id).join("、")}>
        {reviewCount.current - result.failures.length}/{reviewCount.current}
      </output>}
      <button type="button" disabled={!ready || progress !== null} onClick={audit}>{progress === null ? "校验" : `${progress}/${reviewCount.current}`}</button>
    </div>
    {file && fileGraph && showFiles && <AssetFilePanel
      key={fileId}
      entry={file}
      entries={fileGraph.entries}
      root={fileGraph.root ?? ""}
      openFile={openFile}
      inspect={inspect}
      selectedPart={inspected?.part}
      back={fileTrail.length > 0 ? goBack : undefined}
      busy={!ready || progress !== null}
    />}
  </main>;
}
