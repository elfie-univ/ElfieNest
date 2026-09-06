import { useEffect, useRef, useState } from "react";
import { Alert, Button, Input, Modal, Select, Slider } from "antd";

import type { BigFive, ElfieListItem, ElfieSession, FoodConfiguration, FoodItem, ModelSubscription, OllamaProbe } from "./contracts";
import { createSubmissionGate, creationAgeError } from "./viewModel";

type FoodManagementView = "list" | "form";
type OllamaProbeView = Readonly<{
  readonly state: "idle" | "checking" | OllamaProbe["state"];
  readonly endpoint: string;
  readonly version: string;
  readonly message: string;
}>;

type Props = Readonly<{
  readonly createOpen: boolean;
  readonly elfieManagementOpen: boolean;
  readonly elfies: readonly ElfieListItem[];
  readonly configurationOpen: boolean;
  readonly foods: readonly FoodItem[];
  readonly modelSubscriptions: readonly ModelSubscription[];
  readonly deleteTarget: ElfieSession | null;
  readonly personalityTarget: ElfieSession | null;
  readonly onCreateClose: () => void;
  readonly onElfieManagementClose: () => void;
  readonly onElfieManagementCreate: () => void;
  readonly onElfieManagementSelect: (id: string) => void;
  readonly onElfieManagementDelete: (id: string) => void;
  readonly onCreate: (creation: Creation) => Promise<boolean | string>;
  readonly onConfigurationClose: () => void;
  readonly onConfigureFood: (configuration: FoodConfiguration) => Promise<string>;
  readonly onDeleteFood: (foodId: string) => Promise<void>;
  readonly onProbeOllama: (apiBase?: string) => Promise<OllamaProbe>;
  readonly onDeleteClose: () => void;
  readonly onDelete: () => void;
  readonly onPersonalityClose: () => void;
  readonly onPersonality: (values: BigFive) => void;
}>;

export type Creation = Readonly<{
  readonly name: string;
  readonly species_id: string;
  readonly age_years: string;
  readonly description: string;
  readonly appearance_description: string;
  readonly personality_description: string;
}>;

const traits: readonly [keyof BigFive, string][] = [
  ["openness", "开放性"],
  ["conscientiousness", "尽责性"],
  ["extraversion", "外向性"],
  ["agreeableness", "宜人性"],
  ["neuroticism", "敏感性"],
];

const initialCreation: Creation = {
  name: "",
  species_id: "dog",
  age_years: "2",
  description: "用于本地调试的单精灵",
  appearance_description: "默认测试外貌",
  personality_description: "",
};

const emptyFoodConfiguration: FoodConfiguration = {
  connection_type: "ollama",
  display_name: "",
  api_base: "",
  api_key: "",
  models: [],
  primary_model: "",
  reasoning_model: "",
  vision_model: "",
  tool_model: "",
  fallback_model: "",
};

const defaultOllamaEndpoint = "http://127.0.0.1:11434";
const emptyOllamaProbe: OllamaProbeView = {
  state: "idle",
  endpoint: defaultOllamaEndpoint,
  version: "",
  message: "",
};

function parseModels(raw: string): readonly string[] {
  const normalized = raw
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return [...new Set(normalized)];
}

function roleOptions(models: readonly string[]): readonly Readonly<{ label: string; value: string }>[] {
  return models.map((model) => ({ label: model, value: model }));
}

function ModalTitle({ eyebrow, title }: Readonly<{ readonly eyebrow: string; readonly title: string }>): React.JSX.Element {
  return <div className="lab-modal-title"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>;
}

function selectedOptionValue(models: readonly string[], value: string, fallback = ""): string {
  return models.includes(value) ? value : fallback;
}

export function ElfieModals(props: Props): React.JSX.Element {
  const [creation, setCreation] = useState<Creation>(initialCreation);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [view, setView] = useState<FoodManagementView>("list");
  const [foodConfiguration, setFoodConfiguration] = useState<FoodConfiguration>(emptyFoodConfiguration);
  const [modelsInput, setModelsInput] = useState("");
  const [configuringFood, setConfiguringFood] = useState(false);
  const [configurationError, setConfigurationError] = useState("");
  const [deletingFoodId, setDeletingFoodId] = useState("");
  const [editingFoodId, setEditingFoodId] = useState<string | null>(null);
  const [ollamaProbe, setOllamaProbe] = useState<OllamaProbeView>(emptyOllamaProbe);
  const ollamaProbeRequest = useRef(0);
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
    setCreation(initialCreation);
    setCreating(false);
    setCreateError("");
    creationGate.current.leave();
  }, [props.createOpen]);

  useEffect(() => {
    if (!props.configurationOpen) return;
    setView("list");
    setEditingFoodId(null);
    setFoodConfiguration({ ...emptyFoodConfiguration });
    setModelsInput("");
    setConfiguringFood(false);
    setConfigurationError("");
    setDeletingFoodId("");
    setOllamaProbe(emptyOllamaProbe);
    ollamaProbeRequest.current += 1;
  }, [props.configurationOpen]);

  useEffect(() => {
    if (props.personalityTarget !== null) {
      setValues(props.personalityTarget.profile.big_five);
    }
  }, [props.personalityTarget]);

  function setFoodValue(name: keyof FoodConfiguration, value: string): void {
    setFoodConfiguration((current) => ({ ...current, [name]: value }));
  }

  async function runOllamaProbe(apiBase?: string): Promise<void> {
    const endpoint = apiBase?.trim() || defaultOllamaEndpoint;
    const requestId = ollamaProbeRequest.current + 1;
    ollamaProbeRequest.current = requestId;
    setOllamaProbe({
      state: "checking",
      endpoint,
      version: "",
      message: "正在检测本机 Ollama…",
    });
    try {
      const result = await props.onProbeOllama(endpoint);
      if (ollamaProbeRequest.current !== requestId) return;
      setOllamaProbe(result);
      setFoodConfiguration((current) => current.connection_type === "ollama"
        ? { ...current, api_base: result.endpoint, api_key: "" }
        : current);
    } catch (error) {
      if (ollamaProbeRequest.current !== requestId) return;
      setOllamaProbe({
        state: "unavailable",
        endpoint,
        version: "",
        message: error instanceof Error ? error.message : "Ollama 检测失败",
      });
    }
  }

  function selectConnectionType(connectionType: FoodConfiguration["connection_type"]): void {
    if (editingFoodId !== null || foodConfiguration.connection_type === connectionType) return;
    setConfigurationError("");
    if (connectionType === "ollama") {
      setFoodConfiguration((current) => ({
        ...current,
        connection_type: "ollama",
        api_base: defaultOllamaEndpoint,
        api_key: "",
      }));
      void runOllamaProbe(defaultOllamaEndpoint);
      return;
    }
    ollamaProbeRequest.current += 1;
    setOllamaProbe(emptyOllamaProbe);
    setFoodConfiguration((current) => ({
      ...current,
      connection_type: "openai",
      api_base: "",
      api_key: "",
    }));
  }

  function selectSubscription(value: string): void {
    setConfigurationError("");
    if (value === "__new_subscription__") {
      setFoodConfiguration((current) => {
        const { subscription_id: _subscriptionId, ...withoutSubscription } = current;
        return {
        ...withoutSubscription,
        subscription_name: "",
        connection_type: "openai",
        api_base: "",
        api_key: "",
        models: [],
        primary_model: "",
        reasoning_model: "",
        vision_model: "",
        tool_model: "",
        fallback_model: "",
        };
      });
      setModelsInput("");
      ollamaProbeRequest.current += 1;
      setOllamaProbe(emptyOllamaProbe);
      return;
    }
    const subscription = props.modelSubscriptions.find((item) => item.id === value);
    if (!subscription) return;
    const models = subscription.models;
    setFoodConfiguration((current) => ({
      ...current,
      subscription_id: subscription.id,
      subscription_name: subscription.display_name,
      connection_type: subscription.connection_type,
      api_base: subscription.api_base,
      api_key: "",
      models,
      primary_model: selectedOptionValue(models, current.primary_model, models[0] ?? ""),
      reasoning_model: selectedOptionValue(models, current.reasoning_model),
      vision_model: selectedOptionValue(models, current.vision_model),
      tool_model: selectedOptionValue(models, current.tool_model),
      fallback_model: selectedOptionValue(models, current.fallback_model),
    }));
    setModelsInput(models.join("\n"));
    if (subscription.connection_type === "ollama") void runOllamaProbe(subscription.api_base || defaultOllamaEndpoint);
    else { ollamaProbeRequest.current += 1; setOllamaProbe(emptyOllamaProbe); }
  }

  function updateOllamaEndpoint(value: string): void {
    setFoodValue("api_base", value);
    ollamaProbeRequest.current += 1;
    setOllamaProbe({
      state: "idle",
      endpoint: value.trim() || defaultOllamaEndpoint,
      version: "",
      message: "地址已修改，请重新检测",
    });
  }

  function updateModelsInput(value: string): void {
    const models = parseModels(value);
    setModelsInput(value);
    setFoodConfiguration((current) => ({
      ...current,
      models,
      primary_model: selectedOptionValue(models, current.primary_model, models[0] ?? ""),
      reasoning_model: selectedOptionValue(models, current.reasoning_model),
      vision_model: selectedOptionValue(models, current.vision_model),
      tool_model: selectedOptionValue(models, current.tool_model),
      fallback_model: selectedOptionValue(models, current.fallback_model),
    }));
  }

  function setCreationValue(name: keyof Creation, value: string): void {
    setCreation((current) => ({ ...current, [name]: value }));
  }

  async function submitCreation(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!creationGate.current.enter()) return;
    const validationError = creationAgeError(creation.age_years, creation.species_id);
    if (validationError !== null) {
      creationGate.current.leave();
      setCreateError(validationError);
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const created = await props.onCreate(creation);
      if (created !== true) setCreateError(typeof created === "string" ? created : "创建失败");
    } finally {
      creationGate.current.leave();
      setCreating(false);
    }
  }

  async function submitFoodConfiguration(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const selectedEditing = editingFoodId;
    const models = parseModels(modelsInput);

    if (!foodConfiguration.display_name.trim()) {
      setConfigurationError("请填写粮食名称");
      return;
    }
    if (models.length === 0) {
      setConfigurationError("请填写至少一个模型 ID");
      return;
    }
    if (!foodConfiguration.subscription_id && !foodConfiguration.subscription_name?.trim()) {
      setConfigurationError("请选择已有模型订阅，或填写新的订阅名称");
      return;
    }
    if (!foodConfiguration.primary_model.trim()) {
      setConfigurationError("请先选择主模型");
      return;
    }
    if (!models.includes(foodConfiguration.primary_model.trim())) {
      setConfigurationError("主模型必须在模型列表内");
      return;
    }

    const roleModels = [
      foodConfiguration.reasoning_model,
      foodConfiguration.vision_model,
      foodConfiguration.tool_model,
      foodConfiguration.fallback_model,
    ];

    if (
      !selectedEditing
      && foodConfiguration.connection_type === "openai"
      && !foodConfiguration.api_base?.trim()
    ) {
      setConfigurationError("请填写 API URL");
      return;
    }
    if (
      foodConfiguration.connection_type === "ollama"
      && ollamaProbe.state !== "healthy"
    ) {
      setConfigurationError("请先确认本机 Ollama 已连接");
      return;
    }

    for (const model of roleModels) {
      if (!model || !model.trim()) continue;
      if (!models.includes(model.trim())) {
        setConfigurationError("角色模型必须在模型列表内");
        return;
      }
    }

    const configuration: FoodConfiguration = {
      ...(selectedEditing ? { food_id: selectedEditing } : {}),
      ...(foodConfiguration.subscription_id ? { subscription_id: foodConfiguration.subscription_id } : {}),
      ...(foodConfiguration.subscription_name?.trim() ? { subscription_name: foodConfiguration.subscription_name.trim() } : {}),
      connection_type: foodConfiguration.connection_type,
      display_name: foodConfiguration.display_name.trim(),
      ...(selectedEditing || foodConfiguration.subscription_id ? {} : {
        api_base: foodConfiguration.api_base?.trim() ?? "",
        ...(foodConfiguration.connection_type === "openai"
          ? { api_key: foodConfiguration.api_key?.trim() ?? "" }
          : {}),
      }),
      models,
      primary_model: foodConfiguration.primary_model.trim(),
      reasoning_model: foodConfiguration.reasoning_model.trim(),
      vision_model: foodConfiguration.vision_model.trim(),
      tool_model: foodConfiguration.tool_model.trim(),
      fallback_model: foodConfiguration.fallback_model.trim(),
    };

    setConfiguringFood(true);
    setConfigurationError("");
    try {
      await props.onConfigureFood(configuration);
      setEditingFoodId(null);
      setView("list");
    } catch (error) {
      setConfigurationError(error instanceof Error ? error.message : "粮食验证或保存失败");
      return;
    } finally {
      setConfiguringFood(false);
    }
  }

  async function removeFood(foodId: string): Promise<void> {
    setDeletingFoodId(foodId);
    try {
      await props.onDeleteFood(foodId);
      if (foodId === editingFoodId) {
        setEditingFoodId(null);
        setView("list");
      }
    } finally {
      setDeletingFoodId("");
    }
  }

  function startAddFood(): void {
    setEditingFoodId(null);
    setFoodConfiguration({
      ...emptyFoodConfiguration,
      subscription_name: "",
      api_base: defaultOllamaEndpoint,
    });
    setModelsInput("");
    setConfigurationError("");
    setOllamaProbe(emptyOllamaProbe);
    setView("form");
    void runOllamaProbe(defaultOllamaEndpoint);
  }

  function startEditFood(food: FoodItem): void {
    setDeletingFoodId("");
    setEditingFoodId(food.key);
    setFoodConfiguration({
      food_id: food.key,
      ...(food.subscription_id ? { subscription_id: food.subscription_id } : {}),
      ...(food.subscription_name ? { subscription_name: food.subscription_name } : {}),
      connection_type: food.connection_type,
      display_name: food.display_name,
      api_base: food.api_base,
      api_key: "",
      models: food.models,
      primary_model: food.primary_model || food.models[0] || "",
      reasoning_model: food.reasoning_model,
      vision_model: food.vision_model,
      tool_model: food.tool_model,
      fallback_model: food.fallback_model,
    });
    setModelsInput(food.models.join("\n"));
    setConfigurationError("");
    setConfiguringFood(false);
    setOllamaProbe(emptyOllamaProbe);
    setView("form");
    if (food.connection_type === "ollama") {
      void runOllamaProbe(food.api_base || defaultOllamaEndpoint);
    }
  }

  const selectedFood = editingFoodId === null ? undefined : props.foods.find((item) => item.key === editingFoodId);
  const modelOptions = parseModels(modelsInput);

  const subscriptionOptions = [
    ...props.modelSubscriptions.filter((item) => item.supports_food).map((item) => ({
      value: item.id,
      label: `${item.display_name} · ${item.connection_type === "ollama" ? "本机 Ollama" : "远程 OpenAI"}`,
    })),
    { value: "__new_subscription__", label: "＋ 新增模型订阅" },
  ];
  const selectedSubscription = props.modelSubscriptions.find((item) => item.id === foodConfiguration.subscription_id);
  const creatingSubscription = !foodConfiguration.subscription_id;

  const selectOptions = roleOptions(modelOptions);
  return <>
    <Modal
      className="lab-modal food-editor-modal"
      closable={!configuringFood}
      footer={null}
      onCancel={() => { if (!configuringFood) props.onConfigurationClose(); }}
      open={props.configurationOpen}
      title={<ModalTitle eyebrow="Elfie Lab · 粮食管理" title={view === "list" ? "粮食管理" : selectedFood ? "编辑粮食" : "新增粮食"} />}
      width={980}
      zIndex={1200}
    >
      {view === "list" ? <>
        <div className="food-management-toolbar"><Button onClick={startAddFood} type="primary">＋ 新增粮食</Button></div>
        <section className="food-management-list" aria-label="粮食列表">
          {props.foods.length === 0 ? <p className="form-empty">还没有粮食。点击上方按钮新增一个。</p> : props.foods.map((item) => <article className="food-management-row" key={item.key}>
            <div className="food-management-row-meta"><strong>{item.display_name}</strong><small>{item.connection_type === "ollama" ? "本机 Ollama" : "OpenAI 兼容接口"} · {item.api_base || "未记录地址"}</small><small>{item.model || "未配置模型"}</small><small>{item.description}</small></div>
            <div className="food-management-row-actions"><Button disabled={configuringFood} onClick={() => startEditFood(item)}>编辑</Button><Button danger disabled={deletingFoodId === item.key} loading={deletingFoodId === item.key} onClick={() => void removeFood(item.key)}>{deletingFoodId === item.key ? "删除中…" : "删除"}</Button></div>
          </article>)}
        </section>
      </> : <form aria-label={selectedFood ? "编辑粮食" : "新增粮食"} className="food-editor-form" onSubmit={(event) => { void submitFoodConfiguration(event); }}>
        <label className="food-editor-wide">粮食名称<Input autoComplete="off" maxLength={80} onChange={(event) => setFoodValue("display_name", event.target.value)} placeholder="例如：日常对话测试粮" required value={foodConfiguration.display_name} /></label>
        <section className="food-subscription-section food-editor-wide" aria-label="模型订阅">
          <label>模型订阅<Select disabled={selectedFood !== undefined} onChange={selectSubscription} options={subscriptionOptions} placeholder="选择已有订阅或新增" value={foodConfiguration.subscription_id || (creatingSubscription ? "__new_subscription__" : null)} /></label>
          {creatingSubscription ? <div className="inline-subscription-fields">
            <label>订阅名称<Input disabled={selectedFood !== undefined} onChange={(event) => setFoodValue("subscription_name", event.target.value)} placeholder="例如：火山引擎订阅" value={foodConfiguration.subscription_name ?? ""} /></label>
            <label>连接方式<Select disabled={selectedFood !== undefined} onChange={(value) => selectConnectionType(value as FoodConfiguration["connection_type"])} options={[{ label: "本机 Ollama", value: "ollama" }, { label: "远程 OpenAI 兼容", value: "openai" }]} value={foodConfiguration.connection_type} /></label>
            <label>API URL<Input autoComplete="url" disabled={selectedFood !== undefined || foodConfiguration.connection_type === "ollama"} onChange={(event) => foodConfiguration.connection_type === "ollama" ? undefined : setFoodValue("api_base", event.target.value)} placeholder={defaultOllamaEndpoint} value={foodConfiguration.api_base ?? ""} /></label>
            <label>API Key（可选）<Input.Password autoComplete="off" disabled={selectedFood !== undefined || foodConfiguration.connection_type === "ollama"} onChange={(event) => setFoodValue("api_key", event.target.value)} placeholder="免鉴权接口可留空" value={foodConfiguration.api_key ?? ""} /></label>
          </div> : <div className="selected-subscription-summary"><strong>{selectedSubscription?.display_name ?? foodConfiguration.subscription_name ?? ""}</strong><span>{selectedSubscription?.api_base || foodConfiguration.api_base || defaultOllamaEndpoint}</span><small>{selectedSubscription?.models.length ?? modelOptions.length} 个模型 · 订阅凭据只读</small></div>}
          {foodConfiguration.connection_type === "ollama" && creatingSubscription ? <section className="ollama-connection-card" aria-live="polite">
          <div className="ollama-connection-summary"><div><span className={`ollama-status-dot ${ollamaProbe.state}`} aria-hidden="true" /><strong>{ollamaProbe.state === "healthy" ? "本机 Ollama 已连接" : ollamaProbe.state === "checking" ? "正在检测本机 Ollama" : "本机 Ollama 未连接"}</strong></div><Button disabled={ollamaProbe.state === "checking"} loading={ollamaProbe.state === "checking"} onClick={() => { void runOllamaProbe(foodConfiguration.api_base); }} size="small">重新检测</Button></div>
          <code>{ollamaProbe.endpoint || foodConfiguration.api_base || defaultOllamaEndpoint}</code>
          <p>{ollamaProbe.message || "默认检测本机 Ollama；不会扫描其他端口。"}{ollamaProbe.version ? ` · v${ollamaProbe.version}` : ""}</p>
          {selectedFood === undefined ? <details className="ollama-advanced-settings"><summary>高级设置：修改本机地址</summary><label>Ollama 地址<Input autoComplete="url" onChange={(event) => updateOllamaEndpoint(event.target.value)} placeholder={defaultOllamaEndpoint} type="url" value={foodConfiguration.api_base ?? ""} /></label><small className="field-help">仅支持本机回环地址和明确端口，例如 http://127.0.0.1:11434。</small><div><Button onClick={() => { updateOllamaEndpoint(defaultOllamaEndpoint); void runOllamaProbe(defaultOllamaEndpoint); }}>恢复默认</Button><Button disabled={ollamaProbe.state === "checking"} onClick={() => { void runOllamaProbe(foodConfiguration.api_base); }}>检测此地址</Button></div></details> : null}
          </section> : null}
          {selectedFood !== undefined ? <small className="field-help">编辑粮食时只能修改角色模型，不会修改订阅凭据或订阅归属。</small> : null}
        </section>
        {creatingSubscription ? <label className="food-editor-wide">模型 ID 列表<Input.TextArea onChange={(event) => updateModelsInput(event.target.value)} placeholder={`每行或逗号一个，例如：\nqwen2.5-7b\nqwen2.5-32b`} required rows={4} value={modelsInput} /><small className="field-help">新订阅的模型列表会与粮食一起保存。</small></label> : null}
        <label>主模型<Select onChange={(value) => setFoodValue("primary_model", value ?? "")} options={[...selectOptions]} placeholder="选择主模型" value={foodConfiguration.primary_model || undefined} /></label>
        <label>推理模型（可选）<Select allowClear onChange={(value) => setFoodValue("reasoning_model", value ?? "")} options={[...selectOptions]} placeholder="沿用主模型" value={foodConfiguration.reasoning_model || undefined} /></label>
        <label>视觉模型（可选）<Select allowClear onChange={(value) => setFoodValue("vision_model", value ?? "")} options={[...selectOptions]} placeholder="不使用视觉" value={foodConfiguration.vision_model || undefined} /></label>
        <label>工具模型（可选）<Select allowClear onChange={(value) => setFoodValue("tool_model", value ?? "")} options={[...selectOptions]} placeholder="不使用工具" value={foodConfiguration.tool_model || undefined} /></label>
        <label>备用模型（可选）<Select allowClear onChange={(value) => setFoodValue("fallback_model", value ?? "")} options={[...selectOptions]} placeholder="不使用备用" value={foodConfiguration.fallback_model || undefined} /></label>
        {configurationError ? <Alert className="food-editor-wide" message={configurationError} showIcon type="error" /> : null}
        <div className="modal-actions food-editor-wide"><Button disabled={configuringFood} onClick={() => setView("list")}>返回列表</Button><Button disabled={foodConfiguration.connection_type === "ollama" && ollamaProbe.state !== "healthy"} htmlType="submit" loading={configuringFood} type="primary">验证并保存</Button></div>
      </form>}
    </Modal>

    <Modal className="lab-modal elfie-management-modal" footer={null} onCancel={props.onElfieManagementClose} open={props.elfieManagementOpen} title={<ModalTitle eyebrow="批量评测 · 测试对象" title="管理测试精灵" />} width={780} zIndex={1200}>
      <div className="elfie-management-toolbar"><span>选择已有精灵，或新建一只用于本次评测。</span><Button onClick={props.onElfieManagementCreate} type="primary">＋ 新建测试精灵</Button></div>
      <section aria-label="测试精灵列表" className="elfie-management-list">{props.elfies.length ? props.elfies.map((item) => <article className="elfie-management-row" key={item.elfie_id}><div><strong>{item.name}</strong><small>{item.species_id === "dog" ? "小狗" : "狐狸"} · {item.elfie_id}</small></div><div><Button onClick={() => props.onElfieManagementSelect(item.elfie_id)}>选择</Button><Button danger onClick={() => props.onElfieManagementDelete(item.elfie_id)}>删除</Button></div></article>) : <p className="form-empty">还没有测试精灵。点击上方按钮新建。</p>}</section>
    </Modal>

    <Modal className="lab-modal" closable={!creating} footer={null} onCancel={() => { if (!creating) props.onCreateClose(); }} open={props.createOpen} title={<ModalTitle eyebrow="独立测试数据" title="新建测试精灵" />} width={680} zIndex={1300}>
      <form aria-label="新建测试精灵" className="lab-form" onSubmit={(event) => { void submitCreation(event); }}>
        <label>精灵物种<Select onChange={(value) => setCreationValue("species_id", value)} options={[{ label: "小狗", value: "dog" }, { label: "狐狸", value: "fox" }]} value={creation.species_id} /></label>
        <label>精灵名称<Input autoComplete="off" maxLength={60} onChange={(event) => setCreationValue("name", event.target.value)} placeholder="给它起一个名字" required value={creation.name} /></label>
        <label>用途描述<Input.TextArea maxLength={240} onChange={(event) => setCreationValue("description", event.target.value)} placeholder="例如：验证普通聊天" required rows={2} value={creation.description} /></label>
        {createError ? <Alert message={createError} showIcon type="error" /> : null}
        <div className="modal-actions"><Button disabled={creating} onClick={props.onCreateClose}>取消</Button><Button htmlType="submit" loading={creating} type="primary">创建并切换</Button></div>
      </form>
    </Modal>

    <Modal className="lab-modal personality-modal" footer={null} onCancel={props.onPersonalityClose} open={props.personalityTarget !== null} title={<ModalTitle eyebrow="创建后校准" title="修改大五人格" />} width={620} zIndex={1300}>
      <form aria-label="修改大五人格" className="lab-form" onSubmit={(event) => { event.preventDefault(); props.onPersonality(values); }}>
        <p className="modal-intro">数值由性格描述自动生成。这里的修改会覆盖当前精灵的五维人格。</p>
        <div className="trait-editor">{traits.map(([key, label]) => <label className="trait-row" key={key}><span>{label}</span><Slider aria-label={label} max={1} min={0} onChange={(value) => setValues((current) => ({ ...current, [key]: value }))} step={0.01} value={values[key]} /><output>{values[key].toFixed(2)}</output></label>)}</div>
        <div className="modal-actions"><Button onClick={props.onPersonalityClose}>取消</Button><Button htmlType="submit" type="primary">保存修改</Button></div>
      </form>
    </Modal>

    <Modal className="lab-modal confirm-modal" footer={null} onCancel={props.onDeleteClose} open={props.deleteTarget !== null} title={<ModalTitle eyebrow="可恢复删除" title="删除测试精灵" />} width={520} zIndex={1300}>
      <form aria-label="删除测试精灵" className="lab-form" onSubmit={(event) => { event.preventDefault(); props.onDelete(); }}><p>确认删除 <strong>{props.deleteTarget?.profile.name}</strong>？它的档案、会话和媒体会移入 Lab 回收区。</p><div className="modal-actions"><Button onClick={props.onDeleteClose}>取消</Button><Button danger htmlType="submit" type="primary">删除</Button></div></form>
    </Modal>
  </>;
}
