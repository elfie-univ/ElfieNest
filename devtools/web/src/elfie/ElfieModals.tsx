import { useEffect, useRef, useState } from "react";

import type { BigFive, ElfieSession } from "./contracts";
import { createSubmissionGate, creationAgeError } from "./viewModel";

export type Creation = Readonly<{
  readonly name: string;
  readonly species_id: string;
  readonly age_years: string;
  readonly description: string;
  readonly appearance_description: string;
  readonly personality_description: string;
}>;

type Props = Readonly<{
  readonly createOpen: boolean;
  readonly deleteTarget: ElfieSession | null;
  readonly personalityTarget: ElfieSession | null;
  readonly onCreateClose: () => void;
  readonly onCreate: (creation: Creation) => Promise<boolean>;
  readonly onDeleteClose: () => void;
  readonly onDelete: () => void;
  readonly onPersonalityClose: () => void;
  readonly onPersonality: (values: BigFive) => void;
}>;

const initial: Creation = {
  name: "",
  species_id: "dog",
  age_years: "",
  description: "",
  appearance_description: "",
  personality_description: "",
};
const traits: readonly [keyof BigFive, string][] = [
  ["openness", "开放性"],
  ["conscientiousness", "尽责性"],
  ["extraversion", "外向性"],
  ["agreeableness", "宜人性"],
  ["neuroticism", "敏感性"],
];

export function ElfieModals(props: Props): React.JSX.Element {
  const [creation, setCreation] = useState<Creation>(initial);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const creationGate = useRef(createSubmissionGate());
  const [values, setValues] = useState<BigFive>({
    openness: 0.5,
    conscientiousness: 0.5,
    extraversion: 0.5,
    agreeableness: 0.5,
    neuroticism: 0.5,
  });
  useEffect(() => {
    if (!props.createOpen) return;
    setCreation(initial);
    setCreating(false);
    setCreateError("");
    creationGate.current.leave();
  }, [props.createOpen]);
  useEffect(() => {
    if (props.personalityTarget !== null) {
      setValues(props.personalityTarget.profile.big_five);
    }
  }, [props.personalityTarget]);

  function set(name: keyof Creation, value: string): void {
    setCreation((current) => ({ ...current, [name]: value }));
  }

  async function submitCreation(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!creationGate.current.enter()) return;
    const validationError = creationAgeError(creation.age_years);
    if (validationError !== null) {
      creationGate.current.leave();
      setCreateError(validationError);
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const created = await props.onCreate(creation);
      if (!created) setCreateError("创建失败，请查看页面提示后重试");
    } finally {
      creationGate.current.leave();
      setCreating(false);
    }
  }

  return <>
    {props.createOpen && <div className="modal-backdrop">
      <form aria-label="新建测试精灵" className="modal" onSubmit={(event) => { void submitCreation(event); }} role="dialog">
        <div className="modal-heading">
          <div><p className="eyebrow">独立测试数据</p><h2>新建测试精灵</h2></div>
          <button aria-label="关闭" disabled={creating} onClick={props.onCreateClose} type="button">×</button>
        </div>
        <label>精灵物种
          <select onChange={(event) => set("species_id", event.target.value)} value={creation.species_id}>
            <option value="dog">小狗</option><option value="fox">狐狸</option>
          </select>
        </label>
        <label>精灵名称<input autoComplete="off" maxLength={60} onChange={(event) => set("name", event.target.value)} placeholder="给它起一个名字" required value={creation.name} /></label>
        <label>年龄（岁）<input max="100" min="0.1" onChange={(event) => set("age_years", event.target.value)} placeholder="例如：2" required step="0.1" type="number" value={creation.age_years} /></label>
        <label>用途与角色<textarea maxLength={240} onChange={(event) => set("description", event.target.value)} placeholder="例如：陪伴我验证日常对话、记忆和动作" required rows={2} value={creation.description} /></label>
        <label>性格描述<textarea maxLength={1000} onChange={(event) => set("personality_description", event.target.value)} placeholder="例如：温柔、安静，但对新事物很好奇" required rows={3} value={creation.personality_description} /></label>
        <label>外貌描述<textarea maxLength={1000} onChange={(event) => set("appearance_description", event.target.value)} placeholder="例如：银白色毛发，耳尖是灰色" required rows={3} value={creation.appearance_description} /></label>
        {createError ? <p className="form-error" role="alert">{createError}</p> : null}
        <div className="modal-actions">
          <button className="secondary-button" disabled={creating} onClick={props.onCreateClose} type="button">取消</button>
          <button className="primary-button" disabled={creating} type="submit">{creating ? "创建中…" : "创建并切换"}</button>
        </div>
      </form>
    </div>}
    {props.personalityTarget !== null && <div className="modal-backdrop">
      <form aria-label="修改大五人格" className="modal personality-modal" onSubmit={(event) => { event.preventDefault(); props.onPersonality(values); }} role="dialog">
        <div className="modal-heading"><div><p className="eyebrow">创建后校准</p><h2>修改大五人格</h2></div><button aria-label="关闭" onClick={props.onPersonalityClose} type="button">×</button></div>
        <p className="modal-intro">数值由性格描述自动生成。这里的修改会覆盖当前精灵的五维人格。</p>
        <div className="trait-editor">{traits.map(([key, label]) => <label className="trait-row" key={key}><span>{label}</span><input aria-label={label} max="1" min="0" onChange={(event) => setValues((current) => ({ ...current, [key]: Number(event.target.value) }))} step="0.01" type="range" value={values[key]} /><output>{values[key].toFixed(2)}</output></label>)}</div>
        <div className="modal-actions"><button className="secondary-button" onClick={props.onPersonalityClose} type="button">取消</button><button className="primary-button" type="submit">保存修改</button></div>
      </form>
    </div>}
    {props.deleteTarget !== null && <div className="modal-backdrop">
      <form aria-label="删除测试精灵" className="modal confirm-modal" onSubmit={(event) => { event.preventDefault(); props.onDelete(); }} role="alertdialog">
        <div className="modal-heading"><div><p className="eyebrow">可恢复删除</p><h2>删除测试精灵</h2></div><button aria-label="关闭" onClick={props.onDeleteClose} type="button">×</button></div>
        <p>确认删除 <strong>{props.deleteTarget.profile.name}</strong>？它的档案、会话和媒体会移入 Lab 回收区。</p>
        <div className="modal-actions"><button className="secondary-button" onClick={props.onDeleteClose} type="button">取消</button><button className="danger-button" type="submit">删除</button></div>
      </form>
    </div>}
  </>;
}
