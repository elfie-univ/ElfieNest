import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Alert, Spin } from "antd";
import { z } from "zod";

import { requestFormJson, requestJson } from "../api/http";
import { DetailPanel } from "./DetailPanel";
import { ElfieModals, type Creation } from "./ElfieModals";
import { ElfieSidebar } from "./ElfieSidebar";
import { configureFoodResponseSchema, elfieListSchema, foodsSchema, mediaSchema, modelSubscriptionsSchema, ollamaProbeSchema, reviewerSubscriptionsSchema, sessionSchema, turnSchema, type BigFive, type ElfieListItem, type ElfieSession, type ElfieTurn, type FoodConfiguration, type FoodItem, type ModelSubscription, type OllamaProbe, type PreviewIntent, type ReviewerSubscription } from "./contracts";
import { TimelinePanel } from "./TimelinePanel";

const EvaluationWorkspace = lazy(() => import("./EvaluationWorkspace").then((module) => ({ default: module.EvaluationWorkspace })));
import {
  buildPreviewCommand,
  createPreviewRequestRegistry,
  type PreviewRequest,
} from "./previewProtocol";
import {
  detailCloseAction,
  selectReadyFoodAfterLoad,
  selectElfieIdAfterLoad,
  type DetailFocus,
} from "./viewModel";
import "./legacy.css";
import "./composer.css";
import "./detail-modal.css";
import "./evaluation.css";
import "./parity.css";

const previewMessageSchema = z.object({ channel: z.literal("elfie-lab"), event: z.string(), action: z.string().optional(), request_id: z.string().optional(), data_url: z.string().optional(), reason: z.string().optional(), intent: z.object({ intent_id: z.string().optional() }).passthrough().optional() });
const deletionSchema = z.object({ next_elfie_id: z.string().nullable() });
type Props = Readonly<{ readonly mode?: "experiment" | "evaluation" }>;
function revision(profile: ElfieSession["profile"]): number {
  if (typeof profile.spec_revision === "number" && Number.isInteger(profile.spec_revision) && profile.spec_revision >= 0) return profile.spec_revision;
  return [...String(profile.updated_at ?? JSON.stringify(profile.appearance))].reduce((hash, character) => ((hash * 31) + character.charCodeAt(0)) >>> 0, 0);
}

export function ElfieLabApp({ mode = "experiment" }: Props): React.JSX.Element {
  const [items, setItems] = useState<readonly ElfieListItem[]>([]);
  const [session, setSession] = useState<ElfieSession | null>(null);
  const [foods, setFoods] = useState<readonly FoodItem[]>([]);
  const [modelSubscriptions, setModelSubscriptions] = useState<readonly ModelSubscription[]>([]);
  const [reviewerSubscriptions, setReviewerSubscriptions] = useState<readonly ReviewerSubscription[]>([]);
  const [food, setFood] = useState("");
  const [notice, setNotice] = useState("");
  const [runtimeWarning, setRuntimeWarning] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [elfieManagementOpen, setElfieManagementOpen] = useState(false);
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ElfieSession | null>(null);
  const [personalityTarget, setPersonalityTarget] = useState<ElfieSession | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [selectedTurn, setSelectedTurn] = useState<ElfieTurn | null>(null);
  const [detailOpen, setDetailOpen] = useState(true);
  const [detailTab, setDetailTab] = useState("摘要");
  const [detailFocus, setDetailFocus] = useState<DetailFocus>("output");
  const [previewStatus, setPreviewStatus] = useState("加载中");
  const [portraitEpoch, setPortraitEpoch] = useState(0);
  const [previewResult, setPreviewResult] = useState<{ readonly turnId: string; readonly intentId: string; readonly status: "completed" | "unsupported"; readonly reason: string } | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const sessionRef = useRef<ElfieSession | null>(null);
  const pendingPreview = useRef(createPreviewRequestRegistry());
  const pendingFoodSelection = useRef<((foodKey: string) => void) | null>(null);
  const pendingElfieSelection = useRef<((elfieId: string) => void) | null>(null);
  const previewReady = useRef(false);
  const configuredPreviewKey = useRef("");

  useEffect(() => { sessionRef.current = session; }, [session]);
  async function load(id?: string | null): Promise<void> {
    const elfies = await requestJson("elfies", elfieListSchema);
    const catalog = await requestJson("runtime/foods", foodsSchema).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "Runtime 粮食目录不可用";
      setRuntimeWarning(message);
      return null;
    });
    const subscriptionCatalog = await requestJson("runtime/model-subscriptions", modelSubscriptionsSchema).catch(() => null);
    setItems(elfies.items);
    const nextFoods = catalog?.items ?? [];
    setFoods(nextFoods);
    const sharedSubscriptions = subscriptionCatalog?.items ?? [];
    setModelSubscriptions(sharedSubscriptions);
    setReviewerSubscriptions(sharedSubscriptions.filter((item) => item.supports_reviewer));
    setFood((current) => selectReadyFoodAfterLoad(current, nextFoods));
    if (catalog !== null) setRuntimeWarning("");
    const selected = selectElfieIdAfterLoad(
      id,
      sessionRef.current?.elfie_id,
      elfies.items[0]?.elfie_id,
    );
    setSession(selected === undefined ? null : await requestJson(`elfies/${encodeURIComponent(selected)}`, sessionSchema));
  }
  useEffect(() => { void load().catch((error: unknown) => setNotice(error instanceof Error ? error.message : "加载失败")); }, []);

  async function configureFood(configuration: FoodConfiguration): Promise<string> {
    try {
      const result = await requestJson("runtime/foods/configure", configureFoodResponseSchema, { method: "post", json: configuration });
      setFoods(result.items);
      const subscriptionCatalog = await requestJson("runtime/model-subscriptions", modelSubscriptionsSchema).catch(() => null);
      const sharedSubscriptions = subscriptionCatalog?.items ?? [];
      setModelSubscriptions(sharedSubscriptions);
      setReviewerSubscriptions(sharedSubscriptions.filter((item) => item.supports_reviewer));
      setFood(result.selected_food);
      pendingFoodSelection.current?.(result.selected_food);
      pendingFoodSelection.current = null;
      setConfigurationOpen(false);
      setNotice("连接验证通过，粮食已保存并选中。");
      return result.selected_food;
    } catch (error) {
      const message = error instanceof Error ? error.message : "粮食验证或保存失败";
      setNotice(message);
      throw error instanceof Error ? error : new Error(message);
    }
  }

  async function probeOllama(apiBase?: string): Promise<OllamaProbe> {
    return requestJson("runtime/ollama/probe", ollamaProbeSchema, {
      method: "post",
      json: apiBase?.trim() ? { api_base: apiBase.trim() } : {},
    });
  }

  function openNewFood(onSaved?: (foodKey: string) => void): void {
    pendingFoodSelection.current = onSaved ?? null;
    setConfigurationOpen(true);
  }

  function openElfieManagement(onSaved?: (elfieId: string) => void): void {
    pendingElfieSelection.current = onSaved ?? null;
    setElfieManagementOpen(true);
  }

  async function saveReviewerSubscription(configuration: Record<string, unknown>): Promise<ReviewerSubscription> {
    const result = await requestJson("runtime/reviewer-subscriptions", z.object({ item: reviewerSubscriptionsSchema.shape.items.element, items: reviewerSubscriptionsSchema.shape.items }), { method: "post", json: configuration, timeout: 30_000 });
    const subscriptionCatalog = await requestJson("runtime/model-subscriptions", modelSubscriptionsSchema);
    setModelSubscriptions(subscriptionCatalog.items);
    setReviewerSubscriptions(subscriptionCatalog.items.filter((item) => item.supports_reviewer));
    return result.item;
  }

  async function deleteReviewerSubscription(subscriptionId: string): Promise<void> {
    await requestJson(`runtime/reviewer-subscriptions/${encodeURIComponent(subscriptionId)}`, z.object({ deleted_subscription: z.string() }), { method: "delete" });
    const result = await requestJson("runtime/model-subscriptions", modelSubscriptionsSchema);
    setModelSubscriptions(result.items);
    setReviewerSubscriptions(result.items.filter((item) => item.supports_reviewer));
  }

  function preview(
    action: string,
    payload: Record<string, unknown> = {},
    reportUnavailable = true,
    metadata: Omit<PreviewRequest, "action"> = {},
  ): void {
    const receiver = frameRef.current?.contentWindow?.elfieLabEnqueue;
    if (receiver === undefined) { if (reportUnavailable) setNotice("3D 预览仍在加载，请稍候再试。"); return; }
    const requestId = crypto.randomUUID();
    const captureElfieId = action === "capture" ? sessionRef.current?.elfie_id : undefined;
    const request = {
      action,
      ...metadata,
      ...(captureElfieId === undefined ? {} : { elfieId: captureElfieId }),
    };
    pendingPreview.current.add(requestId, request);
    const commandPayload = captureElfieId === undefined
      ? payload
      : { ...payload, elfie_id: captureElfieId };
    receiver(JSON.stringify(buildPreviewCommand(requestId, action, commandPayload)));
  }
  function configure(current: ElfieSession | null = sessionRef.current): void {
    if (current === null || !previewReady.current) return;
    const key = `${current.profile.elfie_id}:${revision(current.profile)}`;
    if (configuredPreviewKey.current === key) return;
    configuredPreviewKey.current = key;
    preview("configure", { elfie_id: current.profile.elfie_id, species_id: current.profile.species_id, spec_revision: revision(current.profile), appearance: current.profile.appearance }, false);
  }
  useEffect(() => {
    function receive(event: MessageEvent<unknown>): void {
      if (event.origin !== window.location.origin || event.source !== frameRef.current?.contentWindow || typeof event.data !== "string") return;
      let decoded: unknown; try { decoded = JSON.parse(event.data); } catch { return; }
      const message = previewMessageSchema.safeParse(decoded); if (!message.success) return;
      const pending = message.data.request_id
        ? pendingPreview.current.complete(message.data.request_id, true)
        : undefined;
      if (message.data.event === "ready") {
        previewReady.current = true;
        setPreviewStatus("引擎已就绪 · 正在装载角色");
        configure();
        return;
      }
      if (message.data.event === "accepted" && pending?.action === "configure") { setPreviewStatus("Godot 已接收 · 正在创建角色"); return; }
      if ((message.data.event === "completed" || message.data.event === "unsupported") && pending !== undefined && message.data.request_id !== undefined) {
        pendingPreview.current.complete(
          message.data.request_id,
          pending.action === "capture" && message.data.event === "completed",
        );
        if (pending.action === "configure") setPreviewStatus(message.data.event === "completed" ? "角色已装载 · 可交互" : "3D 角色装载失败");
        if (pending.action === "configure" && message.data.event === "unsupported") configuredPreviewKey.current = "";
        if (pending.action === "preview_intent" && pending.turnId && pending.intentId) setPreviewResult({ turnId: pending.turnId, intentId: pending.intentId, status: message.data.event, reason: message.data.reason ?? "" });
        if (message.data.event === "unsupported" && pending.action !== "configure") setNotice(`3D 操作未完成：${message.data.reason ?? "unsupported"}`);
      }
      if (message.data.event !== "portrait" || message.data.data_url === undefined) return;
      const capture = message.data.request_id
        ? pendingPreview.current.complete(message.data.request_id)
        : undefined;
      const id = capture?.elfieId;
      if (capture?.action !== "capture" || id === undefined) return;
      void requestJson(`elfies/${encodeURIComponent(id)}/portrait`, z.object({ portrait_url: z.string() }), { method: "put", json: { data_url: message.data.data_url } }).then((result) => {
        setPortraitEpoch((current) => current + 1);
        setItems((current) => current.map((item) => item.elfie_id === id ? { ...item, portrait_url: result.portrait_url } : item));
        setSession((current) => current?.elfie_id === id ? { ...current, profile: { ...current.profile, portrait_url: result.portrait_url } } : current);
        setNotice("头像已保存。");
      }, (error: unknown) => setNotice(error instanceof Error ? error.message : "头像保存失败"));
    }
    window.addEventListener("message", receive); return () => window.removeEventListener("message", receive);
  }, []);
  useEffect(() => { if (session !== null) configure(session); }, [session]);

  async function create(creation: Creation): Promise<boolean> {
    try {
      const created = await requestJson("elfies", sessionSchema, { method: "post", json: { ...creation, age_years: Number(creation.age_years) } });
      setSession(created);
      setCreateOpen(false);
      pendingElfieSelection.current?.(created.elfie_id);
      pendingElfieSelection.current = null;
      await load(created.elfie_id);
      setNotice("测试精灵已创建。");
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "创建失败");
      return false;
    }
  }
  async function requestDelete(id: string): Promise<void> { if (sessionRef.current?.elfie_id === id) { setDeleteTarget(sessionRef.current); return; } try { setDeleteTarget(await requestJson(`elfies/${encodeURIComponent(id)}`, sessionSchema)); } catch (error) { setNotice(error instanceof Error ? error.message : "无法读取待删除精灵"); } }
  async function remove(): Promise<void> { if (deleteTarget === null) return; try { const result = await requestJson(`elfies/${encodeURIComponent(deleteTarget.elfie_id)}`, deletionSchema, { method: "delete" }); setDeleteTarget(null); if (sessionRef.current?.elfie_id === deleteTarget.elfie_id) { sessionRef.current = null; setSession(null); configuredPreviewKey.current = ""; } await load(result.next_elfie_id); setNotice("测试精灵已移入回收区。"); } catch (error) { setNotice(error instanceof Error ? error.message : "删除失败"); } }
  async function personality(values: BigFive): Promise<void> { if (session === null) return; try { setSession(await requestJson(`elfies/${session.elfie_id}/personality`, sessionSchema, { method: "patch", json: values })); setPersonalityTarget(null); setNotice("人格参数已保存。"); } catch (error) { setNotice(error instanceof Error ? error.message : "保存失败"); } }
  async function upload(file: File): Promise<{ readonly id: string; readonly mimeType: string }> { if (session === null) throw new Error("请先创建测试精灵"); const form = new FormData(); form.set("file", file); const media = await requestFormJson(`elfies/${session.elfie_id}/media`, mediaSchema, { method: "post", form }); return { id: media.media_id, mimeType: media.mime_type }; }
  async function send(body: Record<string, unknown>): Promise<boolean> { if (session === null) return false; try { const turn = await requestJson(`elfies/${session.elfie_id}/turns`, turnSchema, { method: "post", json: body, timeout: 190_000 }); setSession((current) => current === null ? null : { ...current, turns: [...current.turns, turn] }); await load(session.elfie_id); setSelectedTurn(turn); setDetailFocus("output"); setDetailTab("摘要"); setDetailOpen(true); setNotice("刺激已发送，结果已加入时间线。"); return true; } catch (error) { setNotice(error instanceof Error ? error.message : "发送失败"); return false; } }
  function selectTurn(turn: ElfieTurn, focus: string): void {
    const selectedFocus: DetailFocus = focus === "input" || focus === "chain" ? focus : "output";
    setSelectedTurn(turn);
    setDetailFocus(selectedFocus);
    setDetailTab(selectedFocus === "chain" ? "链路" : "摘要");
    setDetailOpen(true);
  }
  function playIntent(turn: ElfieTurn, intent: PreviewIntent): void { if (!intent.intent_id) return; setSelectedTurn(turn); setDetailFocus("output"); setDetailTab("摘要"); setDetailOpen(true); preview("preview_intent", { intent }, true, { turnId: turn.turn_id, intentId: intent.intent_id }); }
  function closeDetail(): void {
    if (detailCloseAction(selectedTurn !== null, sessionRef.current !== null) === "show-live") {
      setSelectedTurn(null);
      setDetailTab("摘要");
      setDetailOpen(true);
      return;
    }
    setDetailOpen(false);
  }

  async function deleteFood(foodId: string): Promise<void> {
    try {
      const result = await requestJson(`runtime/foods/${encodeURIComponent(foodId)}`, z.object({ deleted_food: z.string() }), { method: "delete" });
      setNotice(`粮食 ${result.deleted_food} 已删除。`);
      if (food === result.deleted_food) setFood("");
      await load(session?.elfie_id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除粮食失败");
    }
  }

  const shellClass = `lab-shell${collapsed ? " left-closed" : ""}${mode === "experiment" && detailOpen ? " detail-open" : ""}${mode === "evaluation" ? " evaluation-mode" : ""}`;
  return <main className={shellClass}>
    {mode === "experiment" ? <>
      <ElfieSidebar collapsed={collapsed} food={food} foods={foods} iframeRef={frameRef} items={items} menuOpen={menuOpen} onCollapse={() => setCollapsed(!collapsed)} onCreate={() => { setMenuOpen(false); setCreateOpen(true); }} onDelete={(id) => { void requestDelete(id); }} onEditPersonality={() => setPersonalityTarget(session)} onFood={setFood} onMenu={() => setMenuOpen(!menuOpen)} onNewFood={() => openNewFood()} onSelect={(id) => { setMenuOpen(false); configuredPreviewKey.current = ""; void load(id); }} portraitEpoch={portraitEpoch} preview={preview} previewStatus={previewStatus} runtimeWarning={runtimeWarning} session={session} />
      <TimelinePanel food={food} onPreviewIntent={playIntent} onSelectTurn={selectTurn} onSend={send} onUpload={upload} portraitEpoch={portraitEpoch} session={session} />
      <DetailPanel focus={detailFocus} initialTab={detailTab} onClose={closeDetail} open={detailOpen} previewResult={previewResult} selectedTurn={selectedTurn} session={session} />
    </> : <Suspense fallback={<section className="evaluation-workspace evaluation-loading" aria-label="Elfie 批量评测"><Spin size="large" tip="正在加载批量评测…"><span /></Spin></section>}><EvaluationWorkspace elfies={items} food={food} foods={foods} reviewerSubscriptions={reviewerSubscriptions} onDeleteReviewerSubscription={deleteReviewerSubscription} onSaveReviewerSubscription={saveReviewerSubscription} onNewFood={openNewFood} onNewElfie={openElfieManagement} session={session} /></Suspense>}
    <ElfieModals configurationOpen={configurationOpen} createOpen={createOpen} deleteTarget={deleteTarget} elfieManagementOpen={elfieManagementOpen} elfies={items} foods={foods} modelSubscriptions={modelSubscriptions} onConfigurationClose={() => { pendingFoodSelection.current = null; setConfigurationOpen(false); }} onConfigureFood={configureFood} onDeleteFood={deleteFood} onCreate={create} onCreateClose={() => setCreateOpen(false)} onElfieManagementClose={() => { pendingElfieSelection.current = null; setElfieManagementOpen(false); }} onElfieManagementCreate={() => { setElfieManagementOpen(false); setCreateOpen(true); }} onElfieManagementDelete={(id) => { pendingElfieSelection.current = null; setElfieManagementOpen(false); void requestDelete(id); }} onElfieManagementSelect={(id) => { pendingElfieSelection.current?.(id); pendingElfieSelection.current = null; setElfieManagementOpen(false); }} onDelete={() => { void remove(); }} onDeleteClose={() => setDeleteTarget(null)} onPersonality={(value) => { void personality(value); }} onPersonalityClose={() => setPersonalityTarget(null)} onProbeOllama={probeOllama} personalityTarget={personalityTarget} />
    {notice ? <Alert className="toast" message={notice} role="status" showIcon type={notice.includes("失败") || notice.includes("错误") || notice.includes("不可用") ? "error" : "success"} /> : null}
  </main>;
}
