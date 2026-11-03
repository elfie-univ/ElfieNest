import { Select } from "antd";
import type { CameraCommand, PreviewCatalog } from "./preview-contracts";
export function EnvironmentToolbar({ catalog, send }: { catalog: PreviewCatalog | null; send: (command: CameraCommand) => void }) {
  return <Select aria-label="时间光照" className="nest-time-select" size="small" disabled={catalog === null} value={catalog?.lighting ?? "lighting-live"} options={[
    { value: "lighting-live", label: "实时" }, { value: "lighting-day", label: "白天" },
    { value: "lighting-night", label: "晚上" }, { value: "lighting-quiet", label: "深夜" },
  ]} onChange={(value: string) => send({ action: "select", view_id: value })} />;
}
