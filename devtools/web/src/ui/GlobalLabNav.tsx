import {
  BarChartOutlined,
  ExperimentOutlined,
  HomeOutlined,
} from "@ant-design/icons";
import { Menu, type MenuProps } from "antd";

import type { LabKind } from "../lab-kind";
import {
  devtoolsRoutes,
  routeHref,
  routePath,
  type DevtoolsRoute,
} from "../routes";

type Props = Readonly<{
  readonly activeRoute: DevtoolsRoute;
  readonly currentKind: LabKind;
  readonly onNavigate: (route: DevtoolsRoute) => void;
}>;

const items: NonNullable<MenuProps["items"]> = [
  { key: devtoolsRoutes.elfieExperiment, icon: <ExperimentOutlined />, label: "单精灵实验", title: "单精灵实验" },
  { key: devtoolsRoutes.elfieEvaluations, icon: <BarChartOutlined />, label: "批量评测", title: "批量评测" },
  { key: devtoolsRoutes.nestExperiment, icon: <HomeOutlined />, label: "精灵巢实验", title: "精灵巢实验" },
];

export function GlobalLabNav({ activeRoute, currentKind, onNavigate }: Props): React.JSX.Element {
  function handleClick(info: Parameters<NonNullable<MenuProps["onClick"]>>[0]): void {
    const route = info.key as DevtoolsRoute;
    const href = routeHref(route, currentKind);
    const target = new URL(href, window.location.href);
    if (target.origin !== window.location.origin) {
      window.location.assign(target.href);
      return;
    }
    window.history.pushState({ route }, "", routePath(route));
    onNavigate(route);
  }

  return <nav className={`global-lab-nav global-lab-nav-${currentKind}`} aria-label="Developer Tools 页面导航">
    <Menu
      aria-label="Developer Tools 页面"
      items={items}
      inlineCollapsed
      mode="inline"
      onClick={handleClick}
      selectedKeys={[activeRoute]}
    />
  </nav>;
}
