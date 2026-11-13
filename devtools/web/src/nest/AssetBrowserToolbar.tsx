import { Button, Cascader, ConfigProvider, Select } from "antd";
import { useMemo } from "react";
import { assetCategories, assetLeaves, assetOptions, assetPath, type AssetCategory, type AssetItem } from "./asset-catalog";

type Props = { selected: AssetItem; select: (item: AssetItem) => void; reset: () => void; ready: boolean; busy?: boolean; categories?: AssetCategory[] };
export function AssetBrowserToolbar({ selected, select, reset, ready, busy = false, categories = assetCategories }: Props) {
  const category = categories.find(item => assetPath(item.children, selected.id).length > 0) ?? categories[0]!;
  const options = useMemo(() => assetOptions(category.children), [category]);
  const path = useMemo(() => assetPath(category.children, selected.id), [category, selected.id]);
  return <ConfigProvider theme={{token:{colorPrimary:category.color}}}>
    <div className="nest-menu-dock"><div className="nest-primary-menu nest-asset-menu" role="toolbar" aria-label="资产选择">
      <Select aria-label="资产分类" disabled={busy} value={category.id} className="nest-asset-category"
        options={categories.map(item => ({value:item.id,label:<span style={{color:item.color}}>{item.label}</span>}))}
        onChange={id => { const next = categories.find(item => item.id === id); if (next) select(assetLeaves(next.children)[0]!); }} />
      <span aria-hidden="true">›</span>
      <Cascader aria-label="具体资产" disabled={busy} className="nest-asset-picker" placement="topLeft" allowClear={false}
        classNames={{popup:{root:"nest-cascade-popup"}}}
        options={options} value={path}
        expandTrigger="click" displayRender={labels => labels.join(" / ")}
        showSearch={{filter:(input,path)=>path.some(item=>String(item.label).includes(input))}}
        onChange={path => { const next = assetLeaves(category.children).find(item => item.id === path.at(-1)); if (next) select(next); }} />
      <Button disabled={!ready || busy} onClick={reset}>复位</Button>
    </div></div>
  </ConfigProvider>;
}
