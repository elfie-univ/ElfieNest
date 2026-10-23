extends SceneTree

const NEST_SCENE := preload("res://rooms/nest.tscn")
const NEST_SCRIPT := preload("res://rooms/nest.gd")
const ESTATE_ASSERTIONS := preload("res://scripts/test/complete_estate_test_support.gd")


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var nest := NEST_SCENE.instantiate() as ModularNest
	root.add_child(nest)
	await process_frame
	await process_frame
	if not _require(nest.get_script() == NEST_SCRIPT, "Nest must own the complete asset directly"):
		return
	var generated := nest.get_node("Generated")
	var estate := generated.get_node_or_null("CompleteEstate")
	if not _require(estate != null, "Nest did not instantiate the complete final estate"):
		return
	if not _require(
		generated.find_children("*", "MeshInstance3D", true, false).size() > 0
			and generated.find_children("*", "MultiMeshInstance3D", true, false).size() > 0,
		"Complete estate geometry or restored instance groups are missing",
	):
		return
	if not _require(
		String(estate.get("restore_error")).is_empty()
			and int(estate.get("multimesh_instance_count")) > 0,
		"Complete estate instance restoration failed",
	):
		return
	for old_node in ["DormRoom_01", "ActivityRoom_01", "PortalRoom", "CorridorFloor", "SemanticAnchors"]:
		if not _require(not generated.has_node(old_node), "Legacy content still built: %s" % old_node):
			return
	var catalog := nest.observer_camera_catalog()
	var cameras := generated.find_children("*", "Camera3D", true, false)
	var meshes := generated.find_children("*", "MeshInstance3D", true, false)
	if not _require(ESTATE_ASSERTIONS.physical_error(nest).is_empty(), "Real collision proxies are missing"):
		return
	for count in [32]:
		var configured := nest.apply_world_config({
			"nest_id": "complete-composition",
			"bed_count": count,
			"world_revision": count,
		})
		if not _require(bool(configured.get("accepted", false)), "Valid capacity metadata was rejected"):
			return
		if not _require(
			nest.get_node("Generated/CompleteEstate") == estate
				and nest.observer_camera_catalog() == catalog
				and generated.find_children("*", "Camera3D", true, false) == cameras,
			"Capacity metadata rebuilt or replaced the fixed complete estate",
		):
			return
		if not _require(generated.find_children("*", "MeshInstance3D", true, false) == meshes,
			"Capacity changes rebuilt physical rooms/furniture"):
			return
		var error := ESTATE_ASSERTIONS.manifest_error(nest, configured["manifest"], count)
		if not _require(error.is_empty(), error):
			return
	print("PASS: eight fixed real rooms, 32 beds/desk chairs, collision proxies and capacity activation")
	quit(0)


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
