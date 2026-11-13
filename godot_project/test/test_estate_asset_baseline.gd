extends SceneTree

const SCENE_PATH := "res://nest/assembly/estate.tscn"
const ESTATE_ASSERTIONS := preload("res://test/complete_estate_test_support.gd")
var _profile: FileAccess
var _start_ms := 0


func _init() -> void:
	call_deferred("_validate")


func _validate() -> void:
	_start_ms = Time.get_ticks_msec()
	var log_path := ProjectSettings.globalize_path("res://../build/estate-load-profile.jsonl")
	_profile = FileAccess.open(log_path, FileAccess.WRITE)
	_checkpoint("start")
	_checkpoint("before_resource_load")
	var resource := load(SCENE_PATH) as PackedScene
	_checkpoint("after_resource_load")
	if resource == null:
		_fail("Estate complete-final scene could not be loaded")
		return
	var estate := resource.instantiate() as Node3D
	_checkpoint("after_scene_instantiate")
	if estate == null:
		_fail("Estate complete-final scene root is not Node3D")
		return
	root.add_child(estate)
	_checkpoint("after_ready_restore")
	await process_frame
	if not bool(estate.get_meta("split_runtime_ready", false)):
		_fail("Split runtime bindings were not restored")
		return
	var complete_final := estate
	for legacy_step_name: String in ["Central garden entry step", "Central garden entry step.001"]:
		var legacy_step := complete_final.find_child(legacy_step_name, true, false)
		if legacy_step is MeshInstance3D and (legacy_step as MeshInstance3D).mesh != null:
			estate.queue_free()
			_fail("Superseded white entrance step is still rendered: %s" % legacy_step_name)
			return
	for floral_step_name: String in [
		"Flower preview | CY R002 curved entrance lower tread",
		"Flower preview | CY R002 curved entrance upper tread",
	]:
		var floral_step := complete_final.find_child(floral_step_name, true, false)
		if not floral_step is MeshInstance3D or (floral_step as MeshInstance3D).mesh == null:
			estate.queue_free()
			_fail("Approved floral entrance step is missing: %s" % floral_step_name)
			return
	if not _check_transforms(estate):
		return
	print("PASS split estate canonical GLB placements, materials, LODs and instances")
	estate.queue_free()
	await process_frame
	OS.set_environment("ELFIENEST_GODOT_MODE", "disabled")
	var main_resource := load("res://main.tscn") as PackedScene
	var main := main_resource.instantiate() as Node3D
	root.add_child(main)
	await process_frame
	await process_frame
	var nest := main.get_node("Nest") as ModularNest
	if nest == null or nest.get_script() != load("res://nest/nest.gd"):
		_fail("Main scene must use the existing ModularNest owner directly")
		return
	if nest.scene_file_path != "res://nest/nest.tscn":
		_fail("Main scene must have one complete-estate Nest entry")
		return
	var integrated := nest.get_node_or_null("Generated/CompleteEstate")
	if integrated == null or not batch_transform_error(integrated).is_empty():
		_fail("Main scene did not build the complete final estate")
		return
	if nest.get_node_or_null("Generated/DormRoom_01") != null:
		_fail("Old procedural rooms must not overlap the complete estate")
		return
	if nest.observation_view_count() != 21 or not nest.select_observer_camera_by_id("dorm-01"):
		_fail("Complete estate observation views are missing")
		return
	nest.reset_observer_camera()
	if not nest.select_observer_overview():
		_fail("Complete estate overview could not be selected")
		return
	var manifest := nest.scene_manifest()
	if nest.bed_count != 32 or nest._anchor_markers.size() != 137 or (manifest.get("zones", []) as Array).size() != 21:
		_fail("Split manifest must retain 32 beds, 21 zones and 137 anchors")
		return
	var manifest_error := ESTATE_ASSERTIONS.manifest_error(nest, manifest, nest.bed_count)
	if not manifest_error.is_empty():
		_fail(manifest_error)
		return
	var physical_error := ESTATE_ASSERTIONS.physical_error(nest)
	if not physical_error.is_empty():
		_fail(physical_error)
		return
	var before_config := nest.observer_camera_catalog()
	var configured := nest.apply_world_config({
		"nest_id": "complete-estate-baseline",
		"bed_count": 32,
		"world_revision": 1,
	})
	if (
		not bool(configured.get("accepted", false))
		or nest.get_node("Generated/CompleteEstate") != integrated
		or nest.observer_camera_catalog() != before_config
	):
		_fail("Capacity configuration must preserve the complete estate and camera catalog")
		return
	manifest_error = ESTATE_ASSERTIONS.manifest_error(nest, configured["manifest"], 32)
	if not manifest_error.is_empty():
		_fail(manifest_error)
		return
	_checkpoint("main_scene_ready")
	print("Complete estate main scene passed: 21 cameras, real collisions/anchors and fixed asset identity")
	main.queue_free()
	await process_frame
	quit(0)


func _check_transforms(estate: Node3D) -> bool:
	var error := batch_transform_error(estate)
	if not error.is_empty():
		_fail(error)
		return false
	return true


static func batch_transform_error(estate: Node3D) -> String:
	return preload("res://test/split_estate_test_support.gd").batch_error(estate)


func _checkpoint(stage: String) -> void:
	var rss: Array = []
	OS.execute("/bin/ps", PackedStringArray(["-o", "rss=", "-p", str(OS.get_process_id())]), rss)
	var entry := {
		"stage": stage,
		"elapsed_ms": Time.get_ticks_msec() - _start_ms,
		"static_bytes": OS.get_static_memory_usage(),
		"rss_kib": str(rss[0]).strip_edges().to_int() if not rss.is_empty() else 0,
	}
	print("ESTATE_PROFILE ", JSON.stringify(entry))
	if _profile != null:
		_profile.store_line(JSON.stringify(entry))
		_profile.flush()


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
