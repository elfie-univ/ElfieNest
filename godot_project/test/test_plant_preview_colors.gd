extends SceneTree

class Preview extends "res://tools/static_asset_review.gd":
	func _ready() -> void:
		pass

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://nest/assembly/asset-index.json"))
	var options: Dictionary = index.previews["source:main-planters"]
	var view := Preview.new()
	root.add_child(view)
	view.current = load("res://nest/furniture/shared/main/main-planters.glb").instantiate()
	view.add_child(view.current)
	if not view.prepare_library(options):
		push_error("Plant library preparation failed"); view.free(); quit(1); return
	var focus: Array = index.fileGraph.entries["source:main-planters"].get("focus", [])
	view.isolate_geometry(focus)
	var expected := 0
	for group: Array in options.groups: expected += group.size()
	if view.visible_geometry() != expected:
		push_error("Plant selection hid authored surfaces: expected %d, got %d" % [expected, view.visible_geometry()])
		view.free(); quit(1); return
	var colored := {}
	var wrong: Array[String] = []
	for node: GeometryInstance3D in view.current.find_children("*", "GeometryInstance3D", true, false):
		var mesh: Mesh = node.mesh if node is MeshInstance3D else node.multimesh.mesh
		var parent: Node = node
		var name := ""
		while parent != view.current and name.is_empty():
			name = parent.get_meta("extras", {}).get("source_name", "")
			parent = parent.get_parent()
		for surface: int in mesh.get_surface_count():
			var active: Material = node.get_active_material(surface) if node is MeshInstance3D else mesh.surface_get_material(surface)
			var has_colors: bool = (mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_COLOR) != 0
			if name == "Floor plant | rounded ceramic planter":
				var pot := active as BaseMaterial3D
				if pot == null or pot.cull_mode != BaseMaterial3D.CULL_BACK:
					wrong.append("Mirrored closed planter must retain outward-facing shading")
			if not name.begins_with("Rubber tree |"):
				if not has_colors and node is MeshInstance3D and node.get_surface_override_material(surface) != null:
					wrong.append("Uncolored plant surface was overridden: " + name)
				continue
			colored[name] = true
			var material := active as BaseMaterial3D
			if not has_colors or material == null or not material.vertex_color_use_as_albedo:
				wrong.append("Authored vertex colors ignored: " + name)
	if colored.size() != 4: wrong.append("Expected leaves, wood, veins and buds")
	view.free()
	if not wrong.is_empty():
		push_error("; ".join(wrong)); quit(1); return
	print("PASS plant preview preserves four authored vertex-color surfaces")
	quit(0)
