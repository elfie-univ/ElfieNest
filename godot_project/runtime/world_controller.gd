class_name NestWorldRuntimeController
extends Node

signal runtime_event(
	event_name: String,
	payload: Dictionary,
	correlation_id: String,
)

var navigation_ready := false
var _nest: ModularNest


func setup(nest: ModularNest) -> void:
	_nest = nest


func configure_world(
	config: Dictionary,
	correlation_id: String,
) -> Dictionary:
	navigation_ready = false
	var result := _nest.apply_world_config(config)
	if not bool(result.get("accepted", false)):
		runtime_event.emit("config_rejected", result, correlation_id)
		return result

	await get_tree().process_frame
	var manifest := result.get("manifest", {}) as Dictionary
	if not _prepare_semantic_anchors(manifest) or not _nest.bake_navigation():
		var failure := {
			"accepted": false,
			"code": "navigation_not_ready",
			"world_revision": _nest.world_revision,
		}
		runtime_event.emit("startup_error", failure, correlation_id)
		return failure
	if not await _wait_for_navigation_sync():
		var sync_failure := {
			"accepted": false,
			"code": "navigation_sync_timeout",
			"world_revision": _nest.world_revision,
		}
		runtime_event.emit("startup_error", sync_failure, correlation_id)
		return sync_failure

	navigation_ready = true
	runtime_event.emit("scene_manifest", manifest, correlation_id)
	runtime_event.emit(
		"world_ready",
		{
			"ready": true,
			"navigation_ready": true,
		},
		correlation_id,
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
		var anchor := raw_anchor as Dictionary
		if bool(anchor.get("active", false)):
			var anchor_id := String(anchor.get("anchor_id", ""))
			if anchor_id.is_empty() or _nest.resolve_anchor(anchor_id) == null:
				return false
	return true
