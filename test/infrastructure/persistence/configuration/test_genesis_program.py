"""Validate published source packages without activating them for adoption."""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from infrastructure.persistence.configuration.documents import (
    BundledConfigSource,
    ConfigDocumentError,
    ConfigDocumentId,
)

ROOT = Path(__file__).resolve().parents[4] / "config"


def test_species_directories_use_world_names_without_changing_runtime_ids() -> None:
    species_root = ROOT / "genesis/species"
    expected = {"saevi": "fox", "tovren": "dog", "myelle": "cat"}
    assert {path.name for path in species_root.iterdir() if path.is_dir()} == set(
        expected
    )
    catalog = yaml.safe_load(
        (species_root / "catalog.yaml").read_text(encoding="utf-8")
    )
    assert {row["package"]: row["species_id"] for row in catalog["species"]} == expected
    for row in catalog["species"]:
        package = row["package"]
        assert row["species_package_id"] == package
        for reference in row["files"].values():
            assert Path(reference).parts[0] == package
            assert (species_root / reference).is_file()
        definition = yaml.safe_load(
            (species_root / row["files"]["definition"]).read_text(encoding="utf-8")
        )
        assert definition["technical_species_id"] == expected[package]
        assert definition["identity"]["godot_package_id"] == expected[package]
        for reference in definition["presentation_images"].values():
            assert (species_root / package / reference).is_file()


def test_registered_source_package_contains_confirmed_parameters() -> None:
    loaded = BundledConfigSource(ROOT).load(ConfigDocumentId.GENESIS_PROGRAM)
    document = loaded.document
    assert loaded.path == ROOT / "genesis/program.yaml"
    assert document["status"] == document["manifest"]["status"] == "published"
    assert len(document["manifest"]["members"]) == 18
    assert not document["manifest"]["publication_blockers"]
    assert {item["id"] for item in document["manifest"]["activation_blockers"]} == {
        "myelle-runtime-readiness",
        "production-cutover",
    }
    rules = document["rules"]
    population = rules["population"]
    assert population["grid_dimensions"] == [10, 10]
    assert population["sample_unit_count"] == 100
    assert population["grid_model_member"] == "knowledge/geography.yaml"
    assert "model_population" not in population
    assert "total_population" not in population
    assert population["selection_order"] == [
        "user_selected_species",
        "uniform_allowed_region",
        "uniform_cell_within_selected_region",
    ]
    assert population["cell_sampling"] == {
        "distribution": "uniform_over_cells_in_selected_region",
        "derive_cells_from": "knowledge/geography.yaml#grid.region_matrix",
    }
    assert population["allowed_species_by_region_ref"] == (
        "knowledge/geography.yaml#regions[].allowed_species"
    )
    assert population["species_selection"] == {
        "source": "user_input",
        "allowlist_is_hard_constraint": True,
        "allowed_regions_from": "regions[].allowed_species",
    }
    assert population["region_sampling"] == {
        "distribution": "uniform_over_allowed_regions_for_selected_species",
        "derive_regions_from": "knowledge/geography.yaml#regions[].allowed_species",
    }
    assert "filter_before_sampling" not in population
    assert (
        population["allocation_status"]["birth_eligible_regions_have_allowed_species"]
        is True
    )
    assert "all_regions_have_allowed_species" not in population["allocation_status"]
    assert "all_cell_pair_topology_computable" not in population["allocation_status"]
    assert (
        rules["world"]["route_geometry_status"] == "endpoints_and_grid_hop_rules_only"
    )
    assert rules["household"]["biological_parent_min_age_gap_local_years"] == 3
    assert rules["learning"]["minimum_start_age_local_years"] == 2
    assert rules["learning"]["model"] == "teacher_apprenticeship"
    assert rules["learning"]["vocations"][-1]["apprenticeship_years"] == 1
    assert rules["learning"]["vocations"][2]["apprenticeship_years"] == 2
    assert rules["arrival"]["duration_local_days"] == 3
    policy = rules["policy"]
    assert policy["candidates"]["target_count"] == 5
    assert policy["candidates"]["invitation_count"] == [1, 3]
    assert policy["candidates"]["max_attempts"] == 12
    assert policy["candidates"]["attempt_scope"] == "one_complete_candidate_attempt"
    assert policy["candidates"]["budget_status"] == "confirmed"
    assert policy["candidates"]["attempt_limit_rule"] == (
        "maximum 12 complete-candidate attempts per five-candidate batch; "
        "internal appearance proposals are excluded"
    )
    assert policy["knowledge"]["mastery_probabilities"]["medium"] == {
        "numerator": 1,
        "denominator": 2,
    }
    assert policy["backtracking"] == {"options_per_choice": 8, "total_backtracks": 64}
    assert policy["episodes"]["status"] == "confirmed"
    assert policy["episodes"]["normal_minimum"] == 5
    assert policy["episodes"]["young_exception"] == "actual_age_feasible_events"
    assert policy["episodes"]["fixed_maximum"] is False
    assert "maximum" not in policy["episodes"]
    assert "episode_count" not in policy
    reproducibility = policy["reproducibility"]
    assert reproducibility["algorithm"] == "sha256-domain-v1"
    assert reproducibility["canonical_input_order"] == [
        "algorithm_version",
        "master_seed",
        "domain",
        "stable_object_or_slot_id",
        "domain_policy_version",
        "attempt_id",
        "draw_counter",
    ]
    assert reproducibility["master_seed"] == {
        "source": "accepted_genesis_reservation",
        "bytes": 32,
        "retained_after_commit": False,
    }
    assert reproducibility["digest_output"] == {
        "bytes": 32,
        "encoding": "lowercase_hex",
    }
    assert reproducibility["retry"]["same_inputs_same_result"] is True
    assert reproducibility["retry"]["replace_seed_on_retry"] is False

    life = rules["life_archetypes"]
    assert life["status"] == "confirmed"
    assert len(life["archetypes"]) == 1
    archetype = life["archetypes"][0]
    assert set(archetype["applicable_species"]) == {"Saevi", "Tovren", "Myelle"}
    assert archetype["region_selection"] == "geography_allowed_regions_for_species"
    assert archetype["place_selection"] == "registered_residence_in_selected_region"
    assert archetype["vocation_options_ref"] == "rules.learning.vocations"
    assert archetype["vocation_selection"] == "actual_apprenticeship_only"
    assert archetype["vocation_ref"] is None
    assert life["non_occupational_paths"][0]["id"] == "household_learning"
    assert life["selection"]["vocation_is_potential_until_qualified"] is True
    apprenticeship_ids = {
        apprenticeship["id"] for apprenticeship in rules["learning"]["apprenticeships"]
    }
    non_occupational_path_ids = {path["id"] for path in life["non_occupational_paths"]}
    for archetype in life["archetypes"]:
        assert archetype["learning_path_ref"] in (
            apprenticeship_ids | non_occupational_path_ids
        )
        assert set(archetype["apprenticeship_refs"]) <= apprenticeship_ids

    names = rules["names"]
    assert names["status"] == "confirmed"
    assert names["formal_species_names"] == ["Saevi", "Tovren", "Myelle"]
    assert names["technical_species_ids"] == {
        "Saevi": "fox",
        "Tovren": "dog",
        "Myelle": "cat",
    }
    reserved = set(names["reserved_names"])
    assert reserved == {"Saevi", "Tovren", "Myelle"}
    private_names = set(names["private_name_lexicon"]["default"])
    private_names.update(
        name
        for values in names["private_name_lexicon"]["species_preference"].values()
        for name in values
    )
    private_names.update(names["private_name_lexicon"]["shared_fallback"])
    assert not reserved & private_names
    assert names["selection"]["generated_name_is_not_identity"] is True

    relationships = rules["relationship_archetypes"]
    assert relationships["status"] == "confirmed"
    assert relationships["contact"]["no_contact_fallback"] == "reject_relationship"
    assert relationships["quantity"]["padding"] is False
    assert relationships["quantity"]["guidance_is_not_quota"] is True
    assert {row["role"] for row in relationships["archetypes"]} >= {
        "family",
        "friend",
        "teacher",
    }
    assert {row["role"] for row in relationships["archetypes"]}.isdisjoint(
        {"departure_guide", "earth_contact"}
    )

    episodes = rules["episode_themes"]
    assert episodes["status"] == "confirmed"
    assert set(episodes["instance_fields"]) == {
        "participants",
        "place_ref",
        "event_time",
        "prerequisite_evidence",
        "outcome",
    }
    assert "future_plan_as_fact" in episodes["forbidden"]
    assert episodes["quantity"]["required_events_first"] is True
    assert {row["id"] for row in episodes["themes"]} >= {
        "early-home",
        "shared-space-choice",
        "departure-decision",
        "arrival-nest",
    }


@pytest.mark.parametrize(
    "attack",
    [
        "hash",
        "missing",
        "escape",
        "duplicate",
        "symlink",
        "status_mismatch",
        "publication_blocker",
        "draft_member",
        "entry_hash",
        "orphan",
    ],
)
def test_preparation_package_fails_closed(tmp_path: Path, attack: str) -> None:
    root = tmp_path / "config"
    shutil.copytree(ROOT / "genesis", root / "genesis")
    entry = root / "genesis/program.yaml"
    data = yaml.safe_load(entry.read_text(encoding="utf-8"))
    member = data["manifest"]["members"][0]
    target = entry.parent / member["path"]
    if attack == "hash":
        target.write_text("changed: true\n", encoding="utf-8")
    elif attack == "missing":
        target.unlink()
    elif attack == "escape":
        member["path"] = "../outside.yaml"
    elif attack == "duplicate":
        data["manifest"]["members"].append(dict(member))
    elif attack == "symlink":
        outside = tmp_path / "outside.yaml"
        shutil.copyfile(target, outside)
        target.unlink()
        target.symlink_to(outside)
    elif attack == "status_mismatch":
        data["status"] = "draft"
    elif attack == "publication_blocker":
        data["manifest"]["publication_blockers"] = [
            {"id": "unresolved", "reason": "source review incomplete"}
        ]
    elif attack == "draft_member":
        member["status"] = "draft"
    elif attack == "orphan":
        (entry.parent / "extra.yaml").write_text("extra: true\n", encoding="utf-8")
    else:
        data["rules"]["population"]["grid_dimensions"] = [20, 20]
    if attack != "entry_hash":
        data["manifest"].pop("content_sha256", None)
        canonical = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        data["manifest"]["content_sha256"] = hashlib.sha256(
            canonical.encode()
        ).hexdigest()
    entry.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigDocumentError):
        BundledConfigSource(root).load(ConfigDocumentId.GENESIS_PROGRAM)


def test_registered_knowledge_is_still_the_existing_161_unit_projection() -> None:
    knowledge = yaml.safe_load(
        (ROOT / "genesis/knowledge/elfaria.yaml").read_text(encoding="utf-8")
    )
    rows = knowledge["knowledge"]
    assert len(rows) == len({row["id"] for row in rows}) == 161
    source = ROOT.parent / knowledge["source"]["path"]
    assert (
        hashlib.sha256(source.read_bytes()).hexdigest() == knowledge["source"]["sha256"]
    )
    assert (
        knowledge["source"]["anchor_format"]
        == "<!-- knowledge-unit: {knowledge_id} -->"
    )
    assert knowledge["source"]["anchor_scope"] == "source_paragraph_or_list_item"
    assert knowledge["source"]["anchor_count"] == 161
    assert knowledge["source"]["anchor_ids_are_stable"] is True
    assert knowledge["source"]["projection"] == "one_to_one_exact_description"
    body = (
        source.read_text(encoding="utf-8")
        .split("## 3. 居民知识正文", 1)[1]
        .split("## 4. 个人知识生成", 1)[0]
    )
    units: list[str] = []
    paragraph: list[str] = []
    anchors = re.findall(r"^<!-- knowledge-unit: ([A-E]-\d+(?:-\d+)?) -->$", body, re.M)
    assert anchors == [row["id"] for row in rows]
    for line in body.splitlines() + [""]:
        if re.fullmatch(r"<!-- knowledge-unit: [A-E]-\d+(?:-\d+)? -->", line):
            continue
        if not line.strip() or line.startswith("#") or line.startswith("- "):
            if paragraph:
                units.append(" ".join(paragraph))
                paragraph = []
            if line.startswith("- "):
                units.append(re.sub(r"^(?:\[[^\]]+\]\s*)+", "", line[2:]).strip())
        else:
            paragraph.append(line.strip())
    assert units == [row["description"] for row in rows]
    program = yaml.safe_load(
        (ROOT / "genesis/program.yaml").read_text(encoding="utf-8")
    )
    ids = {row["id"] for row in rows}
    assert set(program["rules"]["arrival"]["knowledge_after_arrival"]) <= ids
    for source_record in program["sources"].values():
        assert (
            hashlib.sha256(
                (ROOT.parent / source_record["path"]).read_bytes()
            ).hexdigest()
            == source_record["sha256"]
        )


def test_preparation_references_are_registered_and_unknown_conditions_block() -> None:
    program = BundledConfigSource(ROOT).load(ConfigDocumentId.GENESIS_PROGRAM).document
    rules = program["rules"]
    world = rules["world"]
    registries = {
        "place": {row["id"] for row in world["places"]},
        "route": {row["id"] for row in world["routes"]},
        "vocation": {row["id"] for row in rules["learning"]["vocations"]},
        "experience": {row["id"] for row in rules["events"]["templates"]},
    }
    assert len(world["places"]) == len(registries["place"]) == 36
    assert len(world["routes"]) == len(registries["route"]) == 16
    for place in world["places"]:
        if "parent" in place:
            assert place["parent"] in registries["place"]
    for route in world["routes"]:
        assert route["from"] in registries["place"]
        assert route["to"] in registries["place"]
        assert route["status"] == "topology_alias"
        assert "registered_distance_km" not in route
        assert "walking_minutes" not in route

    knowledge = yaml.safe_load((ROOT / "genesis/knowledge/elfaria.yaml").read_text())
    unresolved = []
    for row in knowledge["knowledge"]:
        for leaf in row.get("eligibility", {}).get("all", []):
            assert len(leaf) == 1
            kind, condition = next(iter(leaf.items()))
            assert kind in registries
            assert condition["id"] in registries[kind]
            if "unresolved" in condition.values():
                unresolved.append(row["id"])
    assert (
        len(unresolved) == program["coverage"]["condition_resolution"]["blocked"] == 0
    )
    knowledge_by_id = {row["id"]: row for row in knowledge["knowledge"]}
    assert knowledge_by_id["B-02-02"]["eligibility"]["all"] == [
        {"place": {"id": "myelle_region", "contact": "residence"}}
    ]
    assert all(
        knowledge_by_id[row_id]["eligibility"]["all"][0]["place"]["contact"]
        == "public_area_visit"
        for row_id in ("B-04-09", "B-04-10")
    )
    assert knowledge_by_id["E-02-08"]["eligibility"]["all"] == [
        {
            "experience": {
                "id": "deep_exploration",
                "status": "completed",
                "scope": "deep_underground",
            }
        }
    ]
    assert knowledge_by_id["E-07-06"]["eligibility"]["all"] == [
        {"place": {"id": "firstroot_tree", "contact": "local_tradition"}}
    ]
    public_b06 = {"B-06-03", "B-06-05", "B-06-09", "B-06-17"}
    assert all("eligibility" not in knowledge_by_id[row_id] for row_id in public_b06)
    assert not program["manifest"]["publication_blockers"]
    assert rules["arrival"]["arrival_facts_only_after_arrival"]
    arrival = rules["arrival"]
    assert arrival["model"] == "one_short_preparation_training"
    assert arrival["requires"] == ["consent_to_arrive", "registered_trip"]
    assert arrival["completion"] == "training_completed"
    assert arrival["result"] == "travel_to_earth_and_arrive"
    roles = {role["id"] for role in rules["people"]["roles"]}
    assert roles == {
        "caregiver",
        "mentor",
    }
    departure = next(
        theme
        for theme in rules["episode_themes"]["themes"]
        if theme["id"] == "departure-decision"
    )
    assert departure["required_knowledge_ids"] == ["E-08"]
    assert "courses" not in rules["learning"]
    for vocation in rules["learning"]["vocations"]:
        assert vocation["id"] in registries["vocation"]
        assert vocation["qualification_evidence"] == ["apprenticeship_completed"]


def test_source_coverage_and_arrival_stage_policy_are_explicit() -> None:
    program = BundledConfigSource(ROOT).load(ConfigDocumentId.GENESIS_PROGRAM).document
    coverage = program["coverage"]["source_coverage"]
    assert program["coverage"]["status"] == "complete"
    assert coverage["status"] == "complete_for_registered_source_sections"
    assert coverage["granularity"] == "source_section_anchor"
    assert coverage["atomic_id_status"] == "section_anchor_contract"
    assert len(coverage["creator_bindings"]) == 41
    assert all(
        binding["source_path"].startswith("docs/.internal/elfaria/")
        for binding in coverage["creator_bindings"]
    )
    projection = coverage["resident_projection"][0]
    assert projection["unit_count"] == 161
    assert projection["disposition"] == "one_to_one_exact_description"

    expected_stages = {"youth", "young_adult", "mature", "elder"}
    for package in ("saevi", "tovren", "myelle"):
        generation = yaml.safe_load(
            (ROOT / f"genesis/species/{package}/generation.yaml").read_text(
                encoding="utf-8"
            )
        )
        policy = generation["earth_transition_eligibility"]["stage_allowlist"]
        assert policy["status"] == "confirmed"
        assert policy["allowed_stages"] == "all_defined_stages"
        assert policy["excluded_stages"] == []
        assert policy["age_restriction"] == "strictly_greater_than_one_local_year"
        assert set(generation["stage_ranges"]) == expected_stages


def test_geography_model_is_complete_and_distances_are_route_based() -> None:
    program = BundledConfigSource(ROOT).load(ConfigDocumentId.GENESIS_PROGRAM).document
    rules = program["rules"]
    geography_path = ROOT / "genesis/knowledge/geography.yaml"
    geography = yaml.safe_load(geography_path.read_text(encoding="utf-8"))

    assert rules["geography"]["id"] == "geography-model.v9"
    assert rules["geography"]["status"] == "grid_hop_time_ready"
    assert rules["geography"]["usable_for_generation"] is True
    assert geography["schema_version"] == 6
    assert geography["knowledge_version"] == "elfaria-geography.v9"
    assert geography["model_status"] == "complete"
    assert geography["publication_ready"] is True

    grid = geography["grid"]
    assert grid["dimensions"] == [10, 10]
    assert grid["unit_count"] == 100
    assert len(grid["region_matrix"]) == 10
    assert all(len(row) == 10 for row in grid["region_matrix"])
    assert geography["validation"]["region_counts"] == {
        "A1": 30,
        "A2": 4,
        "B": 19,
        "C1": 8,
        "C2": 8,
        "C3": 6,
        "D": 8,
        "E": 8,
        "X": 9,
    }
    counts = {
        region: sum(row.count(region) for row in grid["region_matrix"])
        for region in geography["regions"]
    }
    assert counts == geography["validation"]["region_counts"]
    assert "sampling_units" not in geography
    assert "land_backbone_edges" not in geography["network"]
    assert len(geography["network"]["water"]["grid_hop_edges"]) == 6
    assert geography["population"]["cell_sampling"] == {
        "distribution": "uniform_over_cells_in_selected_region",
        "derive_cells_from": "grid.region_matrix",
    }
    assert geography["population"]["selection_order"] == [
        "user_selected_species",
        "uniform_allowed_region",
        "uniform_cell_within_selected_region",
    ]
    assert "filter_before_sampling" not in rules["population"]
    assert {
        region: geography["regions"][region]["allowed_species"]
        for region in geography["regions"]
    } == {
        "A1": ["Myelle"],
        "A2": ["Myelle"],
        "B": ["Saevi"],
        "C1": ["Tovren"],
        "C2": ["Tovren"],
        "C3": ["Tovren"],
        "D": ["Saevi", "Tovren", "Myelle"],
        "E": [],
        "X": [],
    }
    assert geography["species_policy"] == {
        "canonical_names": ["Saevi", "Tovren", "Myelle"],
        "allowed_species_source": "regions[].allowed_species",
        "region_allowlist_is_hard_constraint": True,
        "selection_source": "user_selected_species",
        "single_species_regions": ["A1", "A2", "B", "C1", "C2", "C3"],
        "central_mixed_region": "D",
        "no_species_regions": ["E", "X"],
        "survival_is_not_personality_or_occupation": True,
    }
    serialized_geography = yaml.safe_dump(geography, allow_unicode=True)
    assert not any(
        re.search(rf"\b{technical_id}\b", serialized_geography)
        for technical_id in ("fox", "dog", "cat")
    )

    place_by_id = {place["id"]: place for place in geography["places"]}
    world_place_ids = {place["id"] for place in rules["world"]["places"]}
    assert set(place_by_id) == world_place_ids
    assert len(place_by_id) == 36
    for place in place_by_id.values():
        assert ("cell" in place) ^ ("regions" in place)
        if "cell" in place:
            assert re.fullmatch(r"R[0-9]C[0-9]", place["cell"])
        else:
            assert set(place["regions"]) <= set(geography["regions"])
    expected_points = {
        "mistyville_center": "R5C4",
        "cloudcrown_city": "R8C5",
        "skymirror_lake": "R8C5",
        "skymirror_trailhead": "R7C4",
        "cloudfall_falls": "R7C5",
        "myelle_tribal_center": "R6C3",
        "saevi_tribal_center": "R5C6",
        "firstroot_tree": "R5C8",
        "earthbound_station": "R4C3",
        "riverturn_hill": "R2C2",
        "riverturn_bend": "R2C3",
        "tovren_tribal_center": "R1C5",
        "lakeheart_isle": "R1C7",
        "clearheart_ferry": "R3C5",
    }
    for place_id, expected_grid in expected_points.items():
        assert place_by_id[place_id]["cell"] == expected_grid
    assert place_by_id["clearheart_lake"]["regions"] == ["E"]

    network = geography["network"]
    assert len(network["land_backbone_paths"]) == 16
    assert ["R0C7", "R0C8", "R0C9"] in network["land_backbone_paths"]
    assert ["R3C1", "R3C2"] in network["land_backbone_paths"]
    path_pairs = {
        tuple(sorted((left, right)))
        for path in network["land_backbone_paths"]
        for left, right in zip(path, path[1:])
    }
    assert len(path_pairs) == 35
    assert network["land_backbone_edge_rule"]["expected_unique_edge_count"] == 35
    assert network["land_backbone_edge_rule"]["expected_unique_node_count"] == 32
    assert len({cell for path in network["land_backbone_paths"] for cell in path}) == 32

    # Resident route-day facts use shortest legal grid hops, then a fixed
    # two-walk-days-per-land-hop conversion.
    region_matrix = geography["grid"]["region_matrix"]
    land_edges = set(path_pairs)
    for row in range(10):
        for column in range(10):
            region = region_matrix[row][column]
            if region in {"E", "X"}:
                continue
            for next_row, next_column in ((row + 1, column), (row, column + 1)):
                if next_row >= 10 or next_column >= 10:
                    continue
                if region_matrix[next_row][next_column] == region:
                    left = f"R{row}C{column}"
                    right = f"R{next_row}C{next_column}"
                    land_edges.add(tuple(sorted((left, right))))
    adjacency: dict[str, set[str]] = {}
    for left, right in land_edges:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)

    def shortest_hops(start: str, destination: str) -> int:
        frontier = [(start, 0)]
        visited = {start}
        for cell, distance in frontier:
            if cell == destination:
                return distance
            for neighbor in adjacency.get(cell, set()) - visited:
                visited.add(neighbor)
                frontier.append((neighbor, distance + 1))
        raise AssertionError(f"No land route: {start} -> {destination}")

    resident = yaml.safe_load(
        (ROOT / "genesis/knowledge/elfaria.yaml").read_text(encoding="utf-8")
    )
    resident_units = {unit["id"]: unit["description"] for unit in resident["knowledge"]}
    for unit_id, start, destination, expected_hops in (
        ("B-04-02", "R5C4", "R5C6", 2),
        ("B-04-03", "R5C4", "R1C5", 5),
        ("B-04-04", "R5C4", "R6C3", 2),
        ("B-04-05", "R5C6", "R5C8", 2),
        ("B-04-06", "R1C5", "R2C2", 4),
        ("B-04-08", "R6C3", "R7C4", 2),
    ):
        assert shortest_hops(start, destination) == expected_hops
        assert f"{expected_hops * 2} 个" in resident_units[unit_id]

    water = network["water"]
    assert set(water["ferry_nodes"]) == {
        "R3C5",
        "R1C5",
        "R0C7",
        "R4C7",
    }
    assert water["connectivity"] == "complete_undirected"
    assert water["expected_edge_count"] == 6
    assert water["grid_hop_edges"] == [
        {"from": "R3C5", "to": "R1C5", "water_grid_hops": 4},
        {"from": "R3C5", "to": "R4C7", "water_grid_hops": 3},
        {"from": "R3C5", "to": "R0C7", "water_grid_hops": 5},
        {"from": "R1C5", "to": "R4C7", "water_grid_hops": 5},
        {"from": "R1C5", "to": "R0C7", "water_grid_hops": 3},
        {"from": "R4C7", "to": "R0C7", "water_grid_hops": 4},
    ]
    assert water["requires_boat_or_ferry"] is True
    assert water["cost_is_higher_than_land"] is True
    assert water["island_destinations"] == [
        {
            "place_id": "lakeheart_isle",
            "cell": "R1C7",
            "from_ferry": "R0C7",
            "mode": "water",
            "water_grid_hops": 1,
        }
    ]
    assert network["local_roads"]["generation"] == "runtime"
    assert network["local_roads"]["no_explicit_cell_edge_list"] is True
    assert network["local_roads"]["cross_region_rule"] == (
        "use_explicit_land_backbone_or_water_route"
    )
    assert "special_edges" not in network
    assert place_by_id["cloudcrown_city"]["access"] == "observation_only"

    kilometer_keys: list[str] = []

    def collect_keys(value: object, path: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith("_km") or key == "distance_km":
                    kilometer_keys.append(f"{path}/{key}")
                collect_keys(child, f"{path}/{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                collect_keys(child, f"{path}[{index}]")

    collect_keys(geography)
    assert kilometer_keys == []
    assert geography["design_boundary"]["kilometer_runtime_fields_forbidden"] is True
    assert geography["validation"]["no_kilometer_runtime_fields"] is True

    source_by_id = {
        artifact["id"]: artifact for artifact in geography["source_artifacts"]
    }
    assert (ROOT.parent / source_by_id["surface-map"]["path"]).exists()
    assert (ROOT.parent / source_by_id["surface-map-route-source"]["path"]).exists()
    assert (ROOT.parent / source_by_id["geography-intermediate"]["path"]).exists()


def test_species_rules_keep_runtime_and_personal_life_boundaries() -> None:
    for package in ("saevi", "tovren", "myelle"):
        root = ROOT / "genesis/species" / package
        generation = yaml.safe_load((root / "generation.yaml").read_text())
        ranges = list(generation["stage_ranges"].values())
        assert ranges[0][0] == 0
        assert all(left[1] == right[0] for left, right in zip(ranges, ranges[1:]))
        endpoint = generation["stage_endpoint_policy"]
        assert endpoint["lower_inclusive"] and endpoint["upper_exclusive"]
        assert endpoint["terminal_age_local_years"] == ranges[-1][1]
        definition = yaml.safe_load((root / "species.yaml").read_text())
        assert (
            "personality"
            in definition["individualization_boundary"]["never_auto_assign"]
        )
        assert not definition["shared_body"]["energy"]["unlimited_absorption"]
        appearance = yaml.safe_load((root / "appearance.yaml").read_text())
        capabilities = appearance["runtime_capabilities"]
        assert not capabilities["presentation_image_proves_runtime_readiness"]
        assert "face" not in appearance["supported_controls"]
        if package == "myelle":
            assert not capabilities["required_assets_present"]
            assert (
                definition["presentation_provenance"]["status"]
                == "author_review_required"
            )
            assert set(definition["presentation_images"]) == {"headshot", "full_body"}
