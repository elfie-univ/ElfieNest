import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ElfieLabApp } from "./elfie/ElfieLabApp";
import { currentLabKind, labKinds } from "./lab-kind";
import { NestLabApp } from "./nest/NestLabApp";
import "./styles.css";

function Application(): React.JSX.Element {
  switch (currentLabKind()) {
    case labKinds.elfie:
      return <ElfieLabApp />;
    case labKinds.nest:
      return <NestLabApp />;
  }
}

const container = document.getElementById("root");
if (container === null) throw new Error("Developer Tool 页面缺少根节点");

createRoot(container).render(
  <StrictMode>
    <Application />
  </StrictMode>,
);
