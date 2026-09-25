import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GenesisReviewBody } from "./GenesisReviewModal";
import { genesisReviewSchema } from "./contracts";

const review = genesisReviewSchema.parse({
  schema_version: 1,
  source: {
    package_id: "elfaria.genesis",
    package_version: "elfaria-genesis.v6",
    content_sha256: "source-digest",
    policy_version: "genesis-policy.v6",
    compiler_version: "genesis-compiler.v0.2",
  },
  summary: {
    knowledge_unit_count: 2,
    selected_knowledge_count: 1,
    not_selected_knowledge_count: 1,
    conditional_knowledge_count: 1,
    episode_count: 1,
    relationship_count: 1,
    place_count: 1,
    place_relation_count: 1,
    travel_path_count: 1,
  },
  knowledge: [
    {
      knowledge_id: "K-01",
      source_text: "Markdown 中的原始知识内容",
      topic: "geography",
      scope: "world",
      level: "common",
      certainty: "high",
      status: "active",
      mastery_difficulty: "",
      eligibility: [],
      acquisition_channels: [],
      conditions: [{ kind: "place", attributes: { place_id: "town" } }],
      prerequisite_ids: [],
      selected: true,
      decision: "eligible_certain",
      reason: "来源条件全部满足",
      access: "allowed",
      exposure: "eligible",
      selected_text: "Memory 中实际写入的知识内容",
      mastery_level: "full",
      acquired_age_years: 3,
      acquired_via: "source_eligibility",
    },
    {
      knowledge_id: "K-02",
      source_text: "暂未写入的原始知识",
      topic: "restricted",
      scope: "world",
      level: "specialist",
      certainty: "high",
      status: "active",
      mastery_difficulty: "medium",
      eligibility: [],
      acquisition_channels: [],
      conditions: [],
      prerequisite_ids: [],
      selected: false,
      decision: "not_mastered",
      reason: "稳定抽样未通过",
      access: "allowed",
      exposure: "eligible",
      selected_text: null,
      mastery_level: null,
      acquired_age_years: null,
      acquired_via: null,
    },
  ],
  life: {
    identity: { age_years_at_adoption: 6 },
    origin: { birth_settlement_id: "forest-home" },
    household: { archetype_id: "small-family" },
    learning: { path_id: "local" },
    vocation: { vocation_id: "care" },
    mobility: { visited_place_ids: ["town"] },
    travel_paths: [["home_to_station", ["F1", "D1"], 4]],
    earth_transition: { invitation_accepted: true },
  },
  episodes: [{ seed_id: "episode:arrival", topic: "arrival", content: "抵达巢穴" }],
  relationships: [{ person_id: "friend", display_name: "好友", role: "friend" }],
  places: [{ place_id: "town", label: "镇中心", kind: "landmark" }],
  place_relations: [{ subject_id: "town", relation: "inside", object_id: "mist-town" }],
  outputs: {
    profile: { age_years: 6, gender: "female", origin_place_label: "森林居住区" },
    selfhood: { identity_core: { resident_role: "resident" } },
    knowledge: [{ seed_id: "K-01", content: "Memory 中实际写入的知识内容" }],
    output_ids: ["genesis:self:elfie"],
    content_hash: "bundle-digest",
  },
});

describe("Genesis same-run review", () => {
  it("shows the original source text beside the selected memory text and decision", () => {
    const markup = renderToStaticMarkup(<GenesisReviewBody review={review} />);

    expect(markup).toContain("K-01");
    expect(markup).toContain("Markdown 中的原始知识内容");
    expect(markup).toContain("Memory 中实际写入的知识内容");
    expect(markup).toContain("来源条件全部满足");
    expect(markup).toContain("知识 1/2");
  });
});
