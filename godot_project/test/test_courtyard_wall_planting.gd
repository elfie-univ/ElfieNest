extends SceneTree
## Check complete shared plant silhouettes, including every batch instance.
const BINDING := preload("res://nest/assembly/glb_placement.gd")
const POSES := preload("res://test/test_lotus_bay.gd")
const PLANTS := "res://nest/courtyard/parts/shared/plant-library.glb"
const CENTER := Vector2(0.0, 6.0)
const LIMIT := 49.58 # Inside the existing wall's minimum inner radius, with clearance.

func _initialize() -> void:
	call_deferred("run")

static func from_buffer(buffer: PackedFloat32Array, at: int) -> Transform3D:
	return Transform3D(Basis(Vector3(buffer[at], buffer[at+4], buffer[at+8]), Vector3(buffer[at+1], buffer[at+5], buffer[at+9]), Vector3(buffer[at+2], buffer[at+6], buffer[at+10])), Vector3(buffer[at+3], buffer[at+7], buffer[at+11]))

static func validate_scene(scene: Node3D) -> Dictionary:
	var total := 0
	var violations := 0
	var maximum := 0.0
	var worst := ""
	for binding: Node in scene.find_children("*", "Node3D", true, false):
		if binding.get_script() != BINDING or binding.library.resource_path != PLANTS: continue
		for slot: int in binding.source_nodes.size():
			var node: Node3D = binding.get_child(slot)
			var mesh: Mesh = node.mesh if node is MeshInstance3D else node.multimesh.mesh
			if mesh == null: return {"error":"Unbound shared plant"}
			var points := PackedVector3Array()
			for surface: int in mesh.get_surface_count():
				points.append_array(mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX])
			var bounds := mesh.get_aabb()
			var base := POSES.pose_in(scene, node)
			var data: Dictionary = binding.instance_batches.get(slot, {})
			var count: int = int(data.instance_count) if not data.is_empty() else 1
			var stride: int = 12 + (4 if data.get("use_colors", false) else 0) + (4 if data.get("use_custom_data", false) else 0)
			total += count
			for i: int in count:
				var pose := base * from_buffer(data.buffer, i * stride) if not data.is_empty() else base
				var box := pose * bounds
				var bound := 0.0
				for corner: int in 8:
					var p := box.get_endpoint(corner)
					bound = maxf(bound, Vector2(p.x, p.z).distance_to(CENTER))
				if bound <= LIMIT: continue
				var radius := 0.0
				for point: Vector3 in points:
					var p := pose * point
					radius = maxf(radius, Vector2(p.x, p.z).distance_to(CENTER))
				if radius > maximum:
					maximum = radius
					worst = "%s/%s:%d" % [scene.name, binding.source_nodes[slot], i]
				if radius > LIMIT + 0.00002: violations += 1
	return {"error":"Plants cross the courtyard wall" if violations > 0 else "", "instances":total, "violations":violations, "max_radius":maximum, "worst":worst}

func run() -> void:
	var report := {}
	var failed := false
	for area: String in ["forest", "waterside", "meadow"]:
		var scene: Node3D = load("res://nest/courtyard/areas/%s/%s-layout.scn" % [area, area]).instantiate()
		root.add_child(scene)
		report[area] = validate_scene(scene)
		failed = failed or not str(report[area].error).is_empty()
		scene.free()
	print("COURTYARD_WALL_PLANTING ", JSON.stringify(report))
	quit(1 if failed else 0)
