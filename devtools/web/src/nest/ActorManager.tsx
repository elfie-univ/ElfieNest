import { Alert, Button, Input, InputNumber, Modal, Popconfirm, Select } from "antd";
import { useState } from "react";
import { actorLabel } from "./ActorPicker";
import { actorSchema, type ActorSpecies, type NestActor } from "./contracts";

type FormValues = { name: string; species: "saevi" | "tovren"; age_years: number; gender: "female" | "male" };
type Props = {
  open: boolean; close: () => void; actors: readonly NestActor[]; species: readonly ActorSpecies[];
  selectActor: (id: string) => void;
  mutate: (path: string, method: "post" | "put" | "delete", json?: unknown) => Promise<unknown>;
};
export function randomActorValues(species: ActorSpecies): FormValues {
  return { name: "", species: species.id, age_years: species.min_age + Math.floor(Math.random() * (species.max_age - species.min_age + 1)), gender: Math.random() < .5 ? "female" : "male" };
}
export function ActorManager({ open, close, actors, species, selectActor, mutate }: Props) {
  const [values, setValues] = useState<FormValues>({ name: "", species: "saevi", age_years: 4, gender: "female" });
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const definition = species.find((item) => item.id === values.species) ?? species[0];
  function newActor() { setError(""); if (definition) setValues(randomActorValues(definition)); }
  async function perform(path: string, method: "post" | "put" | "delete", json?: unknown) {
    setBusy(true); setError("");
    try { const result = await mutate(path, method, json); if (method !== "delete") { selectActor(actorSchema.parse(result).actor_id); setAdding(false); } newActor(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败"); }
    finally { setBusy(false); }
  }
  return <Modal title={adding ? "添加精灵" : "管理精灵"} open={open} onCancel={() => { if (!busy) { setAdding(false); setError(""); close(); } }} footer={null} width={520} destroyOnHidden>
    {!adding ? <>
    <div className="nest-actor-list" aria-label="测试精灵列表">{actors.map((actor) => <div className="nest-actor-row" key={actor.actor_id}>
      <span>{actorLabel(actor)}<small>{actor.age_years} 岁 · {actor.gender === "female" ? "雌性" : "雄性"}</small></span>
      <Button size="small" disabled={busy} onClick={() => { selectActor(actor.actor_id); close(); }}>选择</Button>
      <Popconfirm title="从场景移除？原实验档案会保留。" okText="移除" cancelText="取消" onConfirm={() => perform(`actors/${encodeURIComponent(actor.actor_id)}`, "delete")}><Button size="small" danger disabled={busy}>从场景移除</Button></Popconfirm>
    </div>)}{actors.length === 0 ? <p>暂无精灵</p> : null}</div>
    {error ? <Alert type="error" showIcon message={error} /> : null}
    <Button type="primary" disabled={busy || species.length === 0} onClick={() => { newActor(); setAdding(true); }}>＋ 添加精灵</Button>
    </> : <div className="nest-actor-form">
      <label>名字<Input aria-label="精灵名字" value={values.name ?? ""} maxLength={64} disabled={busy} placeholder="可选，留空自动命名" onChange={(event) => setValues({ ...values, name: event.target.value })} /></label>
      <label>物种<Select aria-label="物种" value={values.species} disabled={busy || species.length === 0} options={species.map((item) => ({ value: item.id, label: item.label }))} onChange={(id: FormValues["species"]) => { const item = species.find((option) => option.id === id); if (item) setValues({ ...randomActorValues(item), name: values.name }); }} /></label>
      <label>年龄<InputNumber<number> aria-label="年龄" value={values.age_years} min={definition?.min_age ?? 2} max={definition?.max_age ?? 100} precision={0} disabled={busy} onChange={(age) => { if (age !== null) setValues({ ...values, age_years: age }); }} /></label>
      <label>性别<Select aria-label="性别" value={values.gender} disabled={busy} options={[{ value: "female", label: "雌性" }, { value: "male", label: "雄性" }]} onChange={(gender: FormValues["gender"]) => setValues({ ...values, gender })} /></label>
      <div className="nest-actor-form-actions"><Button disabled={busy} onClick={() => { setError(""); setAdding(false); }}>返回列表</Button><Button disabled={busy || !definition} onClick={() => { if (definition) setValues({ ...randomActorValues(definition), name: values.name }); }}>随机填写</Button><Button type="primary" loading={busy} disabled={!definition} onClick={() => { void perform("actors", "post", { ...values, name: values.name?.trim() || undefined }); }}>创建并保存</Button></div>
      {error ? <Alert type="error" showIcon message={error} /> : null}
    </div>}
  </Modal>;
}
