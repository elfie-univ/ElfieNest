import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Input, Modal, Segmented, Tabs, Tag } from "antd";

import { requestJson } from "../api/http";
import { genesisReviewSchema, type ElfieSession, type GenesisReview } from "./contracts";
import "./genesis-review.css";

type Props = Readonly<{
  readonly target: ElfieSession | null;
  readonly onClose: () => void;
}>;

type KnowledgeFilter = "全部" | "已选" | "未选";

function decisionLabel(decision: string): string {
  const labels: Record<string, string> = {
    mandatory: "生成策略规定必须纳入",
    eligible_certain: "条件满足，纳入",
    medium_mastery: "中等难度抽样通过，纳入",
    not_eligible: "地点或经历条件未满足",
    not_yet_eligible: "抵达事件尚未完成",
    not_mastered: "中等难度抽样未通过",
    selected_by_prerequisite_closure: "作为已选知识的前置知识纳入",
    boundary: "作为未知边界纳入",
    none: "资格不符，未纳入",
  };
  return labels[decision] ?? decision;
}

function json(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function KnowledgeReview({ review }: Readonly<{ review: GenesisReview }>): React.JSX.Element {
  const [filter, setFilter] = useState<KnowledgeFilter>("已选");
  const [query, setQuery] = useState("");
  const items = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return review.knowledge.filter((item) => {
      if (filter === "已选" && !item.selected) return false;
      if (filter === "未选" && item.selected) return false;
      if (!normalized) return true;
      return [item.knowledge_id, item.topic, item.source_text, item.reason]
        .some((value) => value.toLocaleLowerCase().includes(normalized));
    });
  }, [filter, query, review.knowledge]);

  return <section className="genesis-review-knowledge">
    <div className="genesis-review-controls">
      <Segmented onChange={(value) => setFilter(value as KnowledgeFilter)} options={["全部", "已选", "未选"]} value={filter} />
      <Input allowClear aria-label="搜索知识单元" onChange={(event) => setQuery(event.target.value)} placeholder="搜索编号、主题、原文或选择理由" value={query} />
      <small>{items.length} / {review.summary.knowledge_unit_count} 个单元</small>
    </div>
    {items.length ? <div className="genesis-review-list">{items.map((item) => <details className="genesis-review-card" key={item.knowledge_id}>
      <summary><strong>{item.knowledge_id}</strong><span>{item.topic}</span><Tag color={item.selected ? "green" : "default"}>{item.selected ? "已选" : "未选"}</Tag></summary>
      <div className="genesis-review-card-body">
        <p><b>原始 Markdown 知识</b>{item.source_text}</p>
        {item.selected ? <p><b>个人知识写入文本</b>{item.selected_text ?? "（无文本）"}</p> : null}
        <dl><dt>决策</dt><dd>{decisionLabel(item.decision)}（{item.decision}）</dd><dt>理由</dt><dd>{item.reason}</dd><dt>访问资格 / 接触</dt><dd>{item.access} / {item.exposure}</dd><dt>范围 / 层级 / 确定性 / 难度</dt><dd>{item.scope} / {item.level} / {item.certainty} / {item.mastery_difficulty || "无额外难度"}</dd><dt>来源资格 / 获取渠道</dt><dd>{item.eligibility.join("、") || "无"} / {item.acquisition_channels.join("、") || "无"}</dd>
          {item.selected ? <><dt>掌握 / 获得年龄 / 来源</dt><dd>{item.mastery_level ?? "—"} / {item.acquired_age_years ?? "未知"} / {item.acquired_via ?? "—"}</dd></> : null}
          <dt>前置知识</dt><dd>{item.prerequisite_ids.length ? item.prerequisite_ids.join("、") : "无"}</dd>
          <dt>条件</dt><dd>{item.conditions.length ? item.conditions.map((condition) => `${condition.kind}: ${Object.entries(condition.attributes).map(([key, value]) => `${key}=${value}`).join(", ")}`).join("；") : "无条件"}</dd>
        </dl>
      </div>
    </details>)}</div> : <p className="genesis-review-empty">没有符合条件的知识单元。</p>}
  </section>;
}

function RecordList({ items, title, summary }: Readonly<{
  readonly items: readonly Record<string, unknown>[];
  readonly title: string;
  readonly summary: (item: Record<string, unknown>, index: number) => string;
}>): React.JSX.Element {
  return <section className="genesis-review-records" aria-label={title}>
    {items.length ? items.map((item, index) => <details className="genesis-review-card" key={`${title}-${String(item.seed_id ?? item.place_id ?? item.person_id ?? index)}`}>
      <summary><strong>{summary(item, index)}</strong><Tag>{index + 1}</Tag></summary>
      <pre>{json(item)}</pre>
    </details>) : <p className="genesis-review-empty">没有生成内容。</p>}
  </section>;
}

function SelfhoodReview({ review }: Readonly<{ review: GenesisReview }>): React.JSX.Element {
  const [showOutput, setShowOutput] = useState(false);
  const projection = review.outputs.selfhood_projection;

  return <>
    <h3>Selfhood 结构化写入值</h3>
    <pre>{json(review.outputs.selfhood)}</pre>
    <div className="genesis-review-selfhood-action">
      <Button aria-expanded={showOutput} onClick={() => setShowOutput((value) => !value)}>
        {showOutput ? "收起组装输出" : "查看组装输出"}
      </Button>
    </div>
    {showOutput ? <section aria-label="Selfhood 组装输出">
      <h3>身份核心输出</h3><pre>{projection.identity_core_text}</pre>
      <h3>人格与表达输出</h3><pre>{projection.adaptive_self_text}</pre>
    </section> : null}
  </>;
}

export function GenesisReviewBody({ review }: Readonly<{ review: GenesisReview }>): React.JSX.Element {
  const { summary, outputs, life, source } = review;
  const mobility = life.mobility;
  const tabs = [
    {
      key: "knowledge", label: `知识 ${summary.selected_knowledge_count}/${summary.knowledge_unit_count}`,
      children: <KnowledgeReview review={review} />,
    },
    {
      key: "episodes", label: `经历 ${summary.episode_count}`,
      children: <><RecordList items={review.episodes} title="生成的经历" summary={(item, index) => `${String(item.seed_id ?? `经历 ${index + 1}`)} · ${String(item.topic ?? "无主题")}`} /><details className="genesis-review-life"><summary>生成人生骨架与路线明细</summary><pre>{json(life)}</pre></details><details className="genesis-review-life"><summary>访问计划（含重复次数、停留、年龄和旅行日）</summary><pre>{json(mobility)}</pre></details></>,
    },
    {
      key: "people-places", label: `关系与地点 ${summary.relationship_count + summary.place_count}`,
      children: <><RecordList items={review.relationships} title="生成的人物关系" summary={(item) => `${String(item.display_name ?? item.person_id ?? "人物")} · ${String(item.role ?? "关系未标注")}`} /><RecordList items={review.places} title="初始地点图谱" summary={(item) => `${String(item.label ?? item.place_id ?? "地点")} · ${String(item.kind ?? "类型未标注")}`} /><RecordList items={review.place_relations} title="地点之间的关系" summary={(item) => `${String(item.subject_id ?? "")} —${String(item.relation ?? "关系")}→ ${String(item.object_id ?? "")}`} /></>,
    },
    {
      key: "selfhood", label: "Profile 与 Selfhood",
      forceRender: true,
      children: <><h3>Profile 身份锚点</h3><pre>{json(outputs.profile)}</pre><SelfhoodReview review={review} /></>,
    },
    {
      key: "source", label: "生成来源",
      children: <><p>这份记录绑定到创建该精灵时实际使用的资料包和编译器版本。</p><pre>{json(source)}</pre><h3>Memory 初始化提交知识</h3><pre>{json(outputs.knowledge)}</pre><h3>Memory 输出清单</h3><pre>{json({ output_ids: outputs.output_ids, content_hash: outputs.content_hash })}</pre></>,
    },
  ];
  return <div className="genesis-review-body">
    <div className="genesis-review-summary">
      <div><strong>{summary.selected_knowledge_count}</strong><span>知识已选</span></div>
      <div><strong>{summary.not_selected_knowledge_count}</strong><span>知识未选</span></div>
      <div><strong>{summary.conditional_knowledge_count}</strong><span>条件知识</span></div>
      <div><strong>{summary.episode_count}</strong><span>经历</span></div>
      <div><strong>{summary.relationship_count}</strong><span>关系</span></div>
      <div><strong>{summary.place_count} / {summary.place_relation_count}</strong><span>地点 / 地点关系</span></div>
    </div>
    <Tabs items={tabs} />
  </div>;
}

export function GenesisReviewModal({ target, onClose }: Props): React.JSX.Element {
  const [review, setReview] = useState<GenesisReview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const elfieId = target?.elfie_id;

  useEffect(() => {
    if (!elfieId) {
      setReview(null);
      setError("");
      return;
    }
    let active = true;
    setLoading(true);
    setReview(null);
    setError("");
    void requestJson(`elfies/${encodeURIComponent(elfieId)}/genesis-review`, genesisReviewSchema)
      .then((value) => { if (active) setReview(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "无法读取此精灵的创建审查记录"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [elfieId]);

  return <Modal className="lab-modal genesis-review-modal" footer={null} onCancel={onClose} open={target !== null} title={<div className="lab-modal-title"><p className="eyebrow">Genesis · 同次创建记录</p><h2>{target ? `审查 ${target.profile.name} 的初始化` : "初始化审查"}</h2></div>} width={1040} zIndex={1350}>
    {loading ? <p role="status">正在读取该精灵的生成记录…</p> : error ? <Alert message={error} showIcon type="error" /> : review ? <GenesisReviewBody review={review} /> : null}
  </Modal>;
}
