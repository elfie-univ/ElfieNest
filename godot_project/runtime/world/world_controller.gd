class_name NestWorldRuntimeController
extends Node

const SEMANTIC_SCENE_INDEX := preload("res://runtime/world/semantic_scene_index.gd")

signal runtime_event(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
)

var navigation_ready := false
var _nest: ModularNest


func setup(nest: ModularNest) -> void:
	_nest = nest


func configure_world(
	config: Dictionary,
	cause_id: String,
) -> Dictionary:
	navigation_ready = false
	var result := _nest.apply_world_config(config)
	if not bool(result.get("accepted", false)):
		runtime_event.emit("config_rejected", result, cause_id)
		return result

	await get_tree().process_frame
	var manifest := result.get("manifest", {}) as Dictionary
	if not _prepare_semantic_anchors(manifest) or not _nest.bake_navigation():
		var failure := {
			"accepted": false,
			"code": "navigation_not_ready",
			"world_revision": _nest.world_revision,
		}
		runtime_event.emit("startup_error", failure, cause_id)
		return failure
	if not await _wait_for_navigation_sync():
		var sync_failure := {
			"accepted": false,
			"code": "navigation_sync_timeout",
			"world_revision": _nest.world_revision,
		}
		runtime_event.emit("startup_error", sync_failure, cause_id)
		return sync_failure

	navigation_ready = true
	runtime_event.emit("scene_manifest", manifest, cause_id)
	runtime_event.emit(
		"world_configured",
		{
			"configured": true,
			"navigation_ready": true,
		},
		cause_id,
	)
	return result


func _wait_for_navigation_sync() -> bool:
	var navigation_map := _nest.get_world_3d().navigation_map
	for _frame in range(30):
		await get_tree().physics_frame
		if (
			NavigationServer3D.map_get_iteration_id(navigation_map) > 0
			and not NavigationServer3D.map_get_regions(navigation_map).is_empty()
		):
			await get_tree().physics_frame
			await get_tree().physics_frame
			return true
	return false


func _prepare_semantic_anchors(manifest: Dictionary) -> bool:
	var raw_anchors: Variant = manifest.get("anchors", [])
	if not raw_anchors is Array:
		return false
	for raw_anchor: Variant in raw_anchors as Array:
		if not raw_anchor is Dictionary:
			return false
	for anchor_id in SEMANTIC_SCENE_INDEX.active_anchor_ids(manifest):
		if _nest.resolve_anchor(anchor_id) == null:
			return false
	return true
