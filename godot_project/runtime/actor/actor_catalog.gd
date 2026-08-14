class_name NestActorCatalog
extends RefCounted


static func normalize(
	nest: ModularNest,
	actor_scenes: Dictionary,
	raw_actors: Variant,
) -> Dictionary:
	if not raw_actors is Array:
		return {"accepted": false, "code": "invalid_actor_catalog"}
	var normalized: Array[Dictionary] = []
	var seen_ids := {}
	for raw_actor: Variant in raw_actors as Array:
		if not raw_actor is Dictionary:
			return {"accepted": false, "code": "invalid_actor"}
		var actor_data := raw_actor as Dictionary
		var actor_id := String(actor_data.get("actor_id", ""))
		var species := String(actor_data.get("species", ""))
		var spawn_anchor_id := String(actor_data.get("spawn_anchor_id", ""))
		var spawn_anchor := nest.resolve_anchor(spawn_anchor_id)
		if (
			actor_id.is_empty()
			or seen_ids.has(actor_id)
			or not actor_scenes.has(species)
			or spawn_anchor == null
			or String(spawn_anchor.get_meta("kind", "")) != "bed"
		):
			return {"accepted": false, "code": "invalid_actor"}
		var raw_appearance: Variant = actor_data.get("appearance", {})
		if not raw_appearance is Dictionary:
			return {"accepted": false, "code": "invalid_appearance"}
		seen_ids[actor_id] = true
		normalized.append({
			"actor_id": actor_id,
			"species": species,
			"spawn_anchor_id": spawn_anchor_id,
			"appearance": raw_appearance,
		})
	normalized.sort_custom(
		func(left: Dictionary, right: Dictionary) -> bool:
			return String(left["actor_id"]) < String(right["actor_id"])
	)
	return {"accepted": true, "actors": normalized}


static func snapshot(
	nest: ModularNest,
	actors_by_id: Dictionary,
	catalog_by_id: Dictionary,
) -> Dictionary:
	var actors: Array[Dictionary] = []
	var actor_ids: Array = actors_by_id.keys()
	actor_ids.sort()
	for actor_id: Variant in actor_ids:
		var fingerprint := String(catalog_by_id.get(actor_id, ""))
		var actor_data: Variant = JSON.parse_string(fingerprint)
		if not actor_data is Dictionary:
			continue
		var actor_instance := actors_by_id[actor_id] as ElfieActor
		actors.append({
			"actor_id": String(actor_id),
			"zone_id": nest.nearest_zone_id(actor_instance.global_position),
			"posture": (
				"walking"
					if not actor_instance.active_command_id.is_empty()
					else "idle"
			),
			"active_command_id": (
				actor_instance.active_command_id
					if not actor_instance.active_command_id.is_empty()
					else null
			),
		})
	return {
		"world_revision": nest.world_revision,
		"actors": actors,
	}
