class_name ObserverPresentationController
extends Node

const MOCK_WANDER_TARGET := preload("res://runtime/actor/mock_wander_target.gd")
const MOCK_COMMAND_PREFIX := "observer-mock-wander-"

var _nest: ModularNest
var _characters: Node3D
var _actor_scenes: Dictionary
var _actors: Dictionary = {}
var _fingerprints: Dictionary = {}
var _pending_motions: Dictionary = {}


func setup(
	nest: ModularNest,
	characters: Node3D,
	actor_scenes: Dictionary,
) -> void:
	_nest = nest
	_characters = characters
	_actor_scenes = actor_scenes


func _process(_delta: float) -> void:
	var pending_ids: Array[String] = []
	for raw_id: Variant in _pending_motions.keys():
		pending_ids.append(String(raw_id))
	for actor_id in pending_ids:
		var actor := _actors.get(actor_id) as ElfieActor
		var entity: Variant = _pending_motions.get(actor_id)
		if actor == null or not entity is Dictionary:
			_pending_motions.erase(actor_id)
			continue
		_apply_motion(actor, entity as Dictionary)


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
		var fingerprint := _render_fingerprint(entity as Dictionary)
		if _actors.has(actor_id) and _fingerprints.get(actor_id, "") == fingerprint:
			_apply_motion(_actors[actor_id] as ElfieActor, entity as Dictionary)
			continue
		_remove_actor(actor_id)
		var actor := _create_actor(actor_id, entity as Dictionary)
		if actor == null:
			continue
		_actors[actor_id] = actor
		_fingerprints[actor_id] = fingerprint
		_apply_motion(actor, entity as Dictionary)

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
	# Keep the temporary observer replay lightweight; movement remains visible even
	# without installing the authority's shared animation library.
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
	return actor


func _render_fingerprint(entity: Dictionary) -> String:
	return JSON.stringify({
		"room_id": entity.get("room_id"),
		"species_id": entity.get("species_id"),
		"appearance": entity.get("appearance", {}),
		"home_anchor_id": entity.get("home_anchor_id"),
	})


func _apply_motion(actor: ElfieActor, entity: Dictionary) -> void:
	var raw_motion: Variant = entity.get("mock_motion", null)
	if raw_motion == null:
		_pending_motions.erase(actor.elfie_id)
		_stop_motion(actor)
		return
	if not raw_motion is Dictionary:
		_pending_motions.erase(actor.elfie_id)
		return
	var motion := raw_motion as Dictionary
	var sequence := int(motion.get("sequence", 0))
	if sequence < 1:
		_pending_motions.erase(actor.elfie_id)
		_stop_motion(actor)
		return
	if int(actor.get_meta("observer_mock_motion_sequence", -1)) == sequence:
		return
	if not actor.active_command_id.is_empty():
		if actor.active_command_id.begins_with(MOCK_COMMAND_PREFIX):
			actor.cancel_navigation("mock_motion_replaced")
		else:
			return
	var mode := String(motion.get("mode", "wander"))
	var target: Variant
	if mode == "sleep":
		var home_anchor := _nest.resolve_anchor(
			String(actor.get_meta("home_anchor_id", ""))
		)
		if home_anchor == null or String(home_anchor.get_meta("kind", "")) != "bed":
			_pending_motions[actor.elfie_id] = entity.duplicate(true)
			_stop_motion(actor)
			return
		target = home_anchor.global_position
	elif mode == "wander":
		var waypoint := int(motion.get("waypoint", -1))
		target = MOCK_WANDER_TARGET.target_for(
			_nest,
			actor,
			waypoint,
			sequence,
		)
	else:
		_pending_motions.erase(actor.elfie_id)
		_stop_motion(actor)
		return
	if not target is Vector3:
		_pending_motions[actor.elfie_id] = entity.duplicate(true)
		_stop_motion(actor)
		return
	var command_suffix := "sleep-%d" % sequence if mode == "sleep" else "%d" % sequence
	var command_id := "%s%s-%s" % [MOCK_COMMAND_PREFIX, actor.elfie_id, command_suffix]
	if not actor.move_to(command_id, target as Vector3, 30.0):
		_pending_motions[actor.elfie_id] = entity.duplicate(true)
		_stop_motion(actor)
		return
	_pending_motions.erase(actor.elfie_id)
	actor.set_meta("observer_mock_motion_sequence", sequence)
	actor.set_physics_process(true)


func _stop_motion(actor: ElfieActor) -> void:
	if actor.active_command_id.begins_with(MOCK_COMMAND_PREFIX):
		actor.cancel_navigation("mock_motion_stopped")
	actor.set_meta("observer_mock_motion_sequence", -1)
	actor.set_physics_process(false)


func _remove_actor(actor_id: String) -> void:
	_pending_motions.erase(actor_id)
	var actor := _actors.get(actor_id) as ElfieActor
	if actor != null:
		if actor.active_command_id.begins_with(MOCK_COMMAND_PREFIX):
			actor.cancel_navigation("observer_actor_removed")
		if actor.get_parent() == _characters:
			_characters.remove_child(actor)
		actor.queue_free()
	_actors.erase(actor_id)
	_fingerprints.erase(actor_id)
