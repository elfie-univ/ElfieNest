extends SceneTree

const SCENE_PATH := "res://rooms/estate/estate.tscn"
const MODEL_PATH := "res://rooms/estate/ElfieNest-complete-final.glb"
const SIDECAR_PATH := "res://rooms/estate/ElfieNest-complete-final.instances.bin"
const EXPECTED_SOURCE_SHA256 := "30c4f8e7889b03b7da61a68b23f7a640c901267ba0de8c314b4678cc819e8e32"
const EXPECTED_GROUP_COUNT := 134
# The cleared roadside family remains declared, with no drawable instances.
const EXPECTED_RENDERED_GROUP_COUNT := 133
const EXPECTED_INSTANCE_COUNT := 214448
const ESTATE_ASSERTIONS := preload("res://scripts/test/complete_estate_test_support.gd")
var _profile: FileAccess
var _start_ms := 0


func _init() -> void:
	call_deferred("_validate")


func _validate() -> void:
	_start_ms = Time.get_ticks_msec()
	var log_path := ProjectSettings.globalize_path("res://../build/estate-load-profile.jsonl")
	_profile = FileAccess.open(log_path, FileAccess.WRITE)
	_checkpoint("start")
	if not ResourceLoader.exists(MODEL_PATH):
		_fail("Complete final GLB is missing or was not imported")
		return
	if not FileAccess.file_exists(SIDECAR_PATH):
		_fail("Complete final MultiMesh instance sidecar is missing")
		return
	for dependency: String in ResourceLoader.get_dependencies(MODEL_PATH):
		if ".png" in dependency or ".jpg" in dependency or ".jpeg" in dependency:
			_fail("Complete final GLB must retain embedded images without extracted texture dependencies")
			return
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
	if estate.get_meta("asset_role", "") != "complete-final":
		estate.free()
		_fail("Estate scene is not marked as the complete final asset")
		return
	if estate.get_meta("source_sha256", "") != EXPECTED_SOURCE_SHA256:
		estate.free()
		_fail("Estate scene source hash marker does not match the current desktop final export")
		return
	root.add_child(estate)
	_checkpoint("after_ready_restore")
	await process_frame
	_checkpoint("after_first_frame")
	if not str(estate.get("restore_error")).is_empty():
		var restore_error := str(estate.get("restore_error"))
		estate.queue_free()
		_fail("Complete final MultiMesh restore failed: %s" % restore_error)
		return
	if estate.get_node_or_null("CompleteFinal") == null:
		estate.queue_free()
		_fail("Complete final GLB instance is missing")
		return
	var complete_final := estate.get_node("CompleteFinal")
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
	if int(estate.get("multimesh_group_count")) != EXPECTED_GROUP_COUNT:
		estate.queue_free()
		_fail("Complete final MultiMesh group count changed")
		return
	if int(estate.get("multimesh_instance_count")) != EXPECTED_INSTANCE_COUNT:
		estate.queue_free()
		_fail("Complete final MultiMesh instance count changed")
		return
	var multimesh_nodes := 0
	var observed_instance_count := 0
	var source_groups := {}
	for child: Node in estate.get_children():
		if child is MultiMeshInstance3D:
			multimesh_nodes += 1
			var multimesh := (child as MultiMeshInstance3D).multimesh
			if multimesh == null:
				estate.queue_free()
				_fail("Complete final MultiMesh node has no MultiMesh resource")
				return
			observed_instance_count += multimesh.instance_count
			source_groups[str(child.get_meta("source_group"))] = true
			if multimesh.instance_count > CompleteEstateFinal.MAX_BATCH_INSTANCES:
				_fail("Full-detail render batch exceeded its bounded instance count")
				return
	if source_groups.size() != EXPECTED_RENDERED_GROUP_COUNT or observed_instance_count != EXPECTED_INSTANCE_COUNT:
		estate.queue_free()
		_fail("Complete final MultiMesh scene shape changed")
		return
	var first_group_count := 0
	for child: Node in estate.get_children():
		if child is MultiMeshInstance3D and child.get_meta("source_group") == "__ELFIE_INST_GROUP_000":
			first_group_count += child.multimesh.instance_count
	if first_group_count != 2418:
		_fail("Sidecar field order regression: first group must have exactly 2418 instances")
		return
	var colored_surfaces := 0
	for child: Node in estate.get_children():
		if not child is MultiMeshInstance3D:
			continue
		var instanced_mesh := (child as MultiMeshInstance3D).multimesh.mesh
		for surface in range(instanced_mesh.get_surface_count()):
			if instanced_mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR:
				colored_surfaces += 1
				var material := instanced_mesh.surface_get_material(surface)
				var keeps_color: bool = material is BaseMaterial3D and material.vertex_color_use_as_albedo
				if material is ShaderMaterial:
					keeps_color = material.shader == load("res://rooms/estate/estate_opaque.gdshader") and bool(material.get_shader_parameter("use_linear_vertex_color"))
				if not keeps_color:
					_fail("Vertex-color material was lost while converting instanced foliage")
					return
	print("Complete estate colored instance surfaces: ", colored_surfaces)
	if not _check_transforms(estate):
		return
	print(
		"Estate complete-final asset passed: one self-contained GLB plus %d MultiMesh groups; instances=%d"
		% [multimesh_nodes, observed_instance_count]
	)
	estate.queue_free()
	await process_frame
	OS.set_environment("ELFIENEST_GODOT_MODE", "disabled")
	var main_resource := load("res://main.tscn") as PackedScene
	var main := main_resource.instantiate() as Node3D
	root.add_child(main)
	await process_frame
	await process_frame
	var nest := main.get_node("Nest") as ModularNest
	if nest == null or nest.get_script() != load("res://rooms/nest.gd"):
		_fail("Main scene must use the existing ModularNest owner directly")
		return
	if nest.scene_file_path != "res://rooms/nest.tscn":
		_fail("Main scene must have one complete-estate Nest entry")
		return
	var integrated := nest.get_node_or_null("Generated/CompleteEstate")
	if integrated == null or int(integrated.get("multimesh_instance_count")) != EXPECTED_INSTANCE_COUNT:
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
	var manifest_error := ESTATE_ASSERTIONS.manifest_error(nest, manifest, nest.bed_count)
	if not manifest_error.is_empty():
		_fail(manifest_error)
		return
	var physical_error := ESTATE_ASSERTIONS.physical_error(nest)
	if not physical_error.is_empty():
		_fail(physical_error)
		return
	var target_resolver := load("res://runtime/actor/mock_wander_target.gd")
	if (
		target_resolver.waypoint_count(nest) != 6
		or target_resolver.target_for(nest, null, 0) != null
	):
		_fail("Mock Wander protocol must retain six targets and reject a missing actor")
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
	var file := FileAccess.open(SIDECAR_PATH, FileAccess.READ)
	file.seek(20)
	var groups := {}
	for child: Node in estate.get_children():
		if child is MultiMeshInstance3D:
			var name := str(child.get_meta("source_group"))
			if not groups.has(name):
				groups[name] = []
			groups[name].append(child)
	for group_index in range(EXPECTED_GROUP_COUNT):
		var name_length := file.get_32()
		var count := file.get_32()
		var group_name := file.get_buffer(name_length).get_string_from_utf8()
		var matrices := file.get_buffer(count * 64).to_float32_array()
		var seen := PackedByteArray()
		seen.resize(count)
		var shared_mesh: Mesh = null
		for node: MultiMeshInstance3D in groups.get(group_name, []):
			var indices: PackedInt32Array = node.get_meta("source_instance_indices")
			var buffer := node.multimesh.buffer
			if indices.size() != node.multimesh.instance_count or indices.size() > CompleteEstateFinal.MAX_BATCH_INSTANCES:
				return "Invalid spatial batch size: " + group_name
			if shared_mesh != null and shared_mesh != node.multimesh.mesh:
				return "Spatial batches duplicated a shared mesh: " + group_name
			shared_mesh = node.multimesh.mesh
			for index in range(indices.size()):
				var sample := indices[index]
				if sample < 0 or sample >= count or seen[sample] != 0:
					return "Spatial batch duplicated/invalid source index: " + group_name
				seen[sample] = 1
				for component in range(12):
					var source_component: int = [0, 4, 8, 12, 1, 5, 9, 13, 2, 6, 10, 14][component]
					if buffer[index * 12 + component] != matrices[sample * 16 + source_component]:
						return "Spatial batch changed a source transform: " + group_name
		if seen.count(1) != count:
			return "Spatial batches omitted source instances: " + group_name
	return ""


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
