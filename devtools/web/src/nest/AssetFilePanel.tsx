import type { AssetCategory } from "./asset-catalog";

type FileLink = {
  id: string;
  count: number;
  unit: string;
  title?: string;
  component?: string;
  paths?: string[];
  targetPaths?: string[];
};

type FileBreakdown = {
  componentMeshBytes: number;
  otherMeshBytes: number;
  variantMeshBytes: number;
  embeddedTextureBytes: number;
  otherFileBytes: number;
};
type FileSize = {
  fileBytes: number;
  referenceBytes: number;
  breakdown?: FileBreakdown;
  referenceFiles?: { path: string; title: string; bytes: number }[];
};
type ComponentSize = { meshBytes: number; textureBytes: number; instances: number; meshCopies?: number };
type Component = {
  id: string;
  title: string;
  count: number;
  paths: string[];
  prototypePaths?: string[];
  size?: ComponentSize;
};

export type AssetFile = {
  title: string;
  file: string;
  kind: "source" | "assembly" | "scene";
  preview: string;
  focus?: string[];
  parts?: FileLink[];
  usedBy?: FileLink[];
  members?: string[];
  components?: Component[];
  detail?: string;
  size?: FileSize;
};

export type AssetFileGraph = {
  root?: string;
  defaults?: Record<string, string>;
  categories?: AssetCategory[];
  entries: Record<string, AssetFile>;
};

type Row = {
  key: string;
  title: string;
  file?: string;
  quantity?: string | undefined;
  paths?: string[] | undefined;
  size?: FileSize | ComponentSize | undefined;
  open: () => void;
};

function formatBytes(bytes: number, precision = 2) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(precision)} MiB`;
  return `${(bytes / 1024 ** 3).toFixed(precision)} GiB`;
}

function sizeLabel(size: FileSize | ComponentSize) {
  if ("meshBytes" in size) return formatBytes(size.meshBytes + size.textureBytes);
  return formatBytes(size.fileBytes + size.referenceBytes, size.breakdown ? 3 : 2);
}

function fileBreakdown(size: FileSize) {
  if (!size.breakdown) return null;
  const { componentMeshBytes, otherMeshBytes, variantMeshBytes, embeddedTextureBytes, otherFileBytes } = size.breakdown;
  const rows = [
    { label: "子部件网格（去重）", bytes: componentMeshBytes },
    { label: componentMeshBytes ? "其他网格" : "网格（去重）", bytes: otherMeshBytes },
    { label: "法线与切线变体", bytes: variantMeshBytes },
    { label: "内嵌贴图", bytes: embeddedTextureBytes },
    { label: "文件结构与其余数据", bytes: otherFileBytes },
    { label: "外置贴图", bytes: size.referenceBytes },
  ];
  return <section aria-label="体积明细">
    <h3>体积明细</h3>
    <dl className="nest-asset-breakdown">
      {rows.filter(row => row.bytes > 0).map(({ label, bytes }) => <div key={label}>
        <dt>{label}</dt>
        <dd title={`${bytes.toLocaleString()} B`}>{formatBytes(bytes, 3)}</dd>
      </div>)}
    </dl>
  </section>;
}

export function AssetFilePanel({
  entry,
  entries,
  root = "",
  openFile,
  inspect,
  selectedPart,
  back,
  busy,
}: {
  entry: AssetFile;
  entries: AssetFileGraph["entries"];
  root?: string;
  openFile: (id: string, paths?: string[], component?: string) => void;
  inspect: (key: string, paths: string[], solo?: boolean) => void;
  selectedPart: string | undefined;
  back: (() => void) | undefined;
  busy: boolean;
}) {
  const isSource = entry.kind === "source";

  function links(rows: FileLink[] = [], prefix: string): Row[] {
    return rows.flatMap(row => {
      const asset = entries[row.id];
      if (!asset) return [];
      const size = row.component ? asset.components?.find(part => part.id === row.component)?.size : asset.size;
      return [{
        key: `${prefix}:${row.id}:${row.component ?? ""}`,
        title: row.title ?? asset.detail ?? asset.title,
        file: root + asset.file,
        quantity: row.unit === "实例" && row.count > 1 ? `×${row.count}` : undefined,
        paths: row.paths,
        size: prefix === "use" ? undefined : size,
        open: () => openFile(row.id, row.targetPaths, row.component),
      }];
    });
  }

  function section(title: string, rows: Row[], openOnClick = false) {
    if (rows.length === 0) return null;
    return <section>
      <h3>{title}</h3>
      <ul>{rows.map(row => {
        const paths = row.paths;
        const size = row.size;
        const label = isSource && size && "meshBytes" in size
          ? formatBytes(size.meshBytes)
          : size && sizeLabel(size);
        const breakdown = !isSource && size && "meshBytes" in size
          ? `单件 · 网格 ${formatBytes(size.meshBytes)} · 贴图 ${formatBytes(size.textureBytes)}`
          : undefined;
        return <li key={row.key} className={openOnClick && paths?.length ? "nest-asset-reference" : undefined}>
          <button
            className="nest-asset-link"
            type="button"
            disabled={busy}
            aria-pressed={!openOnClick && paths?.length ? selectedPart === row.key : undefined}
            onClick={() => !openOnClick && paths?.length ? inspect(row.key, paths) : row.open()}
            onDoubleClick={!openOnClick && paths?.length ? row.open : undefined}
            onKeyDown={event => {
              if (!openOnClick && event.key === "Enter" && paths?.length) {
                event.preventDefault();
                row.open();
              }
            }}
          >
            <span>
              {row.title}
              {row.file && <small className="nest-asset-path" title={row.file}>{row.file.split("/").at(-1)}</small>}
            </span>
            {(label || row.quantity) && <span className="nest-asset-measure" title={breakdown}>
              {label && <span>{label}</span>}
              {row.quantity && <small>{row.quantity}</small>}
            </span>}
          </button>
          {openOnClick && paths?.length ? <button
            className="nest-asset-highlight"
            type="button"
            aria-label={`高亮${row.title}`}
            aria-pressed={selectedPart === row.key}
            disabled={busy}
            onClick={() => inspect(row.key, paths)}
          >高亮</button> : null}
        </li>;
      })}</ul>
    </section>;
  }

  const components = entry.components?.map(part => {
    const instances = part.size?.instances ?? part.count;
    const copies = part.size?.meshCopies;
    return {
      key: part.id,
      title: part.title,
      quantity: copies !== undefined && copies < instances
        ? `${instances} 处 · 共用 ${copies} 套网格`
        : `${instances} 个`,
      paths: part.paths,
      size: part.size,
      open: () => inspect(part.id, part.prototypePaths ?? part.paths, true),
    };
  });
  const members = links(entry.members?.map(id => ({ id, count: 0, unit: "" })), "member");

  return <aside
    className="nest-asset-details"
    aria-label="文件与引用"
    onKeyDown={event => {
      if (event.key === "Escape" && selectedPart) inspect("", []);
    }}
  >
    <header>
      <span className="nest-asset-file-type">{entry.file.split(".").at(-1)?.toUpperCase()}</span>
      {back && <button type="button" onClick={back} disabled={busy}>返回</button>}
      <h2>{entry.title}</h2>
      <small className="nest-asset-path">{root + entry.file}</small>
      {entry.size && <>
        <p className="nest-asset-total">
          <span>总大小</span>
          <strong title={`${(entry.size.fileBytes + entry.size.referenceBytes).toLocaleString()} B`}>{sizeLabel(entry.size)}</strong>
        </p>
        {entry.size.referenceBytes > 0 && <p><small>文件 {formatBytes(entry.size.fileBytes)} · {isSource ? "外置贴图" : "引用"} {formatBytes(entry.size.referenceBytes)}</small></p>}
      </>}
    </header>
    {entry.size && fileBreakdown(entry.size)}
    {!!entry.size?.referenceFiles?.length && <details>
      <summary>{isSource ? "外置贴图明细" : "引用文件明细（去重）"}</summary>
      <dl className="nest-asset-breakdown">
        {entry.size.referenceFiles.map(({ path, title, bytes }) => <div key={path}>
          <dt className="nest-asset-path" title={root + path}>{title}</dt>
          <dd title={`${bytes.toLocaleString()} B`}>{formatBytes(bytes, 3)}</dd>
        </div>)}
      </dl>
    </details>}
    {isSource ? section("子部件", components ?? members) : section("引用", links(entry.parts, "ref"), true)}
    {!isSource && section("分区查看", members)}
    {section("被引用", links(entry.usedBy, "use"))}
  </aside>;
}
