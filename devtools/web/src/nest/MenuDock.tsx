import { Button, ConfigProvider, Select } from "antd";
import { CaretRightOutlined, PauseOutlined, UnorderedListOutlined } from "@ant-design/icons";
import type { Dispatch, ReactNode } from "react";
import { CascadeSeparator } from "./ActorPicker";
import type { MenuEvent, MenuPanel, MenuState } from "./menu-state";

type Props = {
  state: MenuState; dispatch: Dispatch<MenuEvent>; playing: boolean; ready: boolean; busy: boolean;
  togglePlayback: () => void; panels: Readonly<Record<MenuPanel, ReactNode>>; environment: ReactNode;
};
export function MenuDock({ state, dispatch, playing, ready, busy, togglePlayback, panels, environment }: Props) {
  return <ConfigProvider theme={{ token: { fontSize: 12 } }} popupMatchSelectWidth={false} select={{ classNames: { popup: { root: "nest-menu-popup" } } }}><div className="nest-menu-dock"><div className="nest-primary-menu" role="toolbar" aria-label="Nest Lab 操作菜单">
    <Select size="small" className="nest-category-select" aria-label="操作分类" value={state.panel} options={[{ value: "view", label: "视角" }, { value: "action", label: "动作" }]} onChange={(panel: MenuPanel) => dispatch({ type: "panel", panel })} />
    <CascadeSeparator />
    <div className="nest-inline-controls">{(["view", "action"] as const).map((id) => <section className="nest-control-panel" aria-label={id === "view" ? "视角操作" : "动作操作"} key={id} hidden={state.panel !== id}>{panels[id]}</section>)}</div>
    <div className="nest-menu-actions"><span className="nest-menu-divider" aria-hidden="true" />{environment}<span className="nest-menu-divider" aria-hidden="true" />
      <Button size="small" className="nest-playback" disabled={!ready || busy} aria-label={playing ? "暂停随机游走" : "播放随机游走"} aria-pressed={playing} icon={playing ? <PauseOutlined /> : <CaretRightOutlined />} onClick={togglePlayback}>{playing ? "暂停" : "播放"}</Button>
      <span className="nest-menu-divider" aria-hidden="true" />
      <Button size="small" aria-label="运行记录" aria-pressed={state.records} aria-controls="nest-run-records" icon={<UnorderedListOutlined />} onClick={() => dispatch({ type: "records" })}>运行记录</Button>
    </div>
  </div></div></ConfigProvider>;
}
