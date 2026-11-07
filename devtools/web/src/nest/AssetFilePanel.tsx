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

type FileSize = { fileBytes: number; referenceBytes: number };
type ComponentSize = { meshBytes: number; textureBytes: number; instances: number };
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

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GiB`;
}

function sizeLabel(size: FileSize | ComponentSize) {
  return formatBytes("meshBytes" in size ? size.meshBytes + size.textureBytes : size.fileBytes + size.referenceBytes);
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
          ? `网格 ${formatBytes(size.meshBytes)} · 贴图 ${formatBytes(size.textureBytes)}`
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

  const components = entry.components?.map(part => ({
    key: part.id,
    title: part.title,
    quantity: `${part.size?.instances ?? part.count} 个`,
    paths: part.paths,
    size: part.size,
    open: () => inspect(part.id, part.prototypePaths ?? part.paths, true),
  }));
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
        <p className="nest-asset-total"><span>总大小</span><strong>{sizeLabel(entry.size)}</strong></p>
        {entry.size.referenceBytes > 0 && <p><small>文件 {formatBytes(entry.size.fileBytes)} · {isSource ? "外置贴图" : "引用"} {formatBytes(entry.size.referenceBytes)}</small></p>}
      </>}
    </header>
    {isSource ? section("子部件", components ?? members) : section("引用", links(entry.parts, "ref"), true)}
    {!isSource && section("分区查看", members)}
    {section("被引用", links(entry.usedBy, "use"))}
  </aside>;
}
