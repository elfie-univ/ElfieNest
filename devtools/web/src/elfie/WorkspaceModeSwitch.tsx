type Props = Readonly<{
  readonly active: "experiment" | "evaluation";
  readonly onExperiment: () => void;
  readonly onEvaluation: () => void;
}>;

export function WorkspaceModeSwitch({ active, onExperiment, onEvaluation }: Props): React.JSX.Element {
  return <nav aria-label="Elfie Lab 工作模式" className="workspace-mode-switch" role="tablist">
    <button aria-selected={active === "experiment"} className={active === "experiment" ? "active" : ""} onClick={onExperiment} role="tab" type="button">单次实验</button>
    <button aria-selected={active === "evaluation"} className={active === "evaluation" ? "active" : ""} onClick={onEvaluation} role="tab" type="button">版本评测</button>
  </nav>;
}
