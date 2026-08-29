import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { ElfieLabApp } from "./elfie/ElfieLabApp";
import { currentLabKind } from "./lab-kind";
import { NestLabApp } from "./nest/NestLabApp";
import { routeFromPath, devtoolsRoutes, type DevtoolsRoute } from "./routes";
import { DevtoolsTheme } from "./ui/DevtoolsTheme";
import { GlobalLabNav } from "./ui/GlobalLabNav";
import "./styles.css";
import "./ui/devtools-antd.css";

function Application(): React.JSX.Element {
  const kind = currentLabKind();
  const [route, setRoute] = useState<DevtoolsRoute>(() => routeFromPath(kind, window.location.pathname));

  useEffect(() => {
    const handlePopState = (): void => setRoute(routeFromPath(kind, window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [kind]);

  const content = route === devtoolsRoutes.nestExperiment
    ? <NestLabApp />
    : <ElfieLabApp mode={route === devtoolsRoutes.elfieEvaluations ? "evaluation" : "experiment"} />;

  return <DevtoolsTheme mode="light">
    <GlobalLabNav activeRoute={route} currentKind={kind} onNavigate={setRoute} />
    {content}
  </DevtoolsTheme>;
}

const container = document.getElementById("root");
if (container === null) throw new Error("Developer Tool 页面缺少根节点");

createRoot(container).render(
  <StrictMode>
    <Application />
  </StrictMode>,
);
