class_name ObserverPresentationController
extends Node

var _nest: ModularNest
var _characters: Node3D
var _actor_scenes: Dictionary
var _actors: Dictionary = {}
var _fingerprints: Dictionary = {}


func setup(
	nest: ModularNest,
	characters: Node3D,
	actor_scenes: Dictionary,
) -> void:
	_nest = nest
	_characters = characters
	_actor_scenes = actor_scenes


func apply_snapshot(snapshot: Dictionary) -> void:
	var entities: Variant = snapshot.get("entities", {})
	if not entities is Dictionary:
		return
	var expected_ids: Dictionary = {}
	for raw_id: Variant in (entities as Dictionary).keys():
		var actor_id := String(raw_id)
		var entity: Variant = (entities as Dictionary).get(raw_id)
		if not entity is Dictionary or not _valid_entity(actor_id, entity as Dictionary):
			continue
		expected_ids[actor_id] = true
		var fingerprint := JSON.stringify(entity)
		if _actors.has(actor_id) and _fingerprints.get(actor_id, "") == fingerprint:
			continue
		_remove_actor(actor_id)
		var actor := _create_actor(actor_id, entity as Dictionary)
		if actor == null:
			continue
		_actors[actor_id] = actor
		_fingerprints[actor_id] = fingerprint

	var stale_ids: Array[String] = []
	for raw_id: Variant in _actors.keys():
		var actor_id := String(raw_id)
		if not expected_ids.has(actor_id):
			stale_ids.append(actor_id)
	for actor_id in stale_ids:
		_remove_actor(actor_id)


func _valid_entity(actor_id: String, entity: Dictionary) -> bool:
	if actor_id.is_empty() or String(entity.get("room_id", "")).strip_edges().is_empty():
		return false
	if typeof(entity.get("active", false)) != TYPE_BOOL or not bool(entity["active"]):
		return false
	var species := String(entity.get("species_id", ""))
	var anchor_id := String(entity.get("home_anchor_id", ""))
	if species.is_empty() or anchor_id.is_empty() or not _actor_scenes.has(species):
		return false
	var anchor := _nest.resolve_anchor(anchor_id)
	if anchor == null or String(anchor.get_meta("kind", "")) != "bed":
		return false
	return entity.get("appearance", {}) is Dictionary


func _create_actor(actor_id: String, entity: Dictionary) -> ElfieActor:
	var species := String(entity["species_id"])
	var scene := _actor_scenes[species] as PackedScene
	var instance := scene.instantiate()
	if not instance is ElfieActor:
		instance.queue_free()
		return null
	var actor := instance as ElfieActor
	actor.install_shared_animations = false
	_characters.add_child(actor)
	var anchor := _nest.resolve_anchor(String(entity["home_anchor_id"]))
	if anchor == null:
		_characters.remove_child(actor)
		actor.queue_free()
		return null
	actor.species_id = species
	actor.configure(actor_id, anchor.global_position, entity["appearance"] as Dictionary)
	actor.ground_visual_to_floor(anchor.global_position.y)
	actor.set_meta("observer_presentation", true)
	actor.set_meta("species", species)
	actor.set_meta("home_anchor_id", String(entity["home_anchor_id"]))
	actor.set_physics_process(false)
	return actor


func _remove_actor(actor_id: String) -> void:
	var actor := _actors.get(actor_id) as ElfieActor
	if actor != null:
		if actor.get_parent() == _characters:
			_characters.remove_child(actor)
		actor.queue_free()
	_actors.erase(actor_id)
	_fingerprints.erase(actor_id)
