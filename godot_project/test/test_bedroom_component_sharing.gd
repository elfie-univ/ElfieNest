extends SceneTree
## Regression contract for the M01 component pilot; no world/runtime startup.

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var scene := load("res://tools/nest_authoring/bedroom-pilot/bedroom.tscn") as PackedScene
	if not require(scene != null, "Bedroom layout must load without build dependencies"): return
	var layout := scene.instantiate() as Node3D
	root.add_child(layout)
	for kind: String in ["bed", "chair"]:
		var reference := layout.get_node(kind + "_A").find_child("part_000", true, false) as MeshInstance3D
		for resident: String in ["B", "C", "D"]:
			var instance := layout.get_node(kind + "_" + resident)
			var part := instance.find_child("part_000", true, false) as MeshInstance3D
			if not require(part.mesh == reference.mesh, "Repeated furniture must share geometry"): return
			if not require(part.get_active_material(0) != reference.get_active_material(0), "Residents must not share mutable material instances"): return
			if not require(str((part.get_meta("extras") as Dictionary).resident) == resident, "Instance resident identity must survive scene nesting"): return
		var meshes := layout.get_node(kind + "_A").find_children("*", "MeshInstance3D", true, false)
		if not require(meshes.size() == (132 if kind == "bed" else 14), "Whole beds keep bedding/pillows, whole chairs keep cushions"): return
	var desks := {}
	for resident: String in ["A", "B", "C", "D"]:
		var instance := layout.get_node("desk_" + resident.to_lower() + "_" + resident)
		desks[instance.scene_file_path] = true
	if not require(desks.size() == 4, "Four fitted desk variants must remain four different scenes"): return
	layout.free()
	print("BEDROOM_COMPONENT_CONTRACT shared geometry, independent materials, four desks, complete beds/chairs")
	quit(0)
