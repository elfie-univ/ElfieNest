extends SceneTree
## Split GLBs own prepared geometry; runtime must retain the shared inputs.

func _initialize() -> void:call_deferred("run")

func run() -> void:
	var source := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(source)
	var checked := 0
	var windows := 0
	var covers := 0
	for placement: Node in preload("res://test/split_estate_test_support.gd").placements(source):
		var prototypes: Dictionary = placement.import_meshes(placement.library.resource_path)
		for index: int in placement.get_child_count():
			var node := placement.get_child(index) as MeshInstance3D
			if node == null: continue
			var extras: Dictionary = node.get_meta("extras", {})
			var window: bool = extras.get("source_name", "") == "ROOM • front fitted deep reveal"
			var cover: bool = extras.get("piece", "") == "bed_cover"
			if not window and not cover: continue
			var original := preload("res://nest/assembly/glb_placement.gd").select_mesh(prototypes, placement.source_nodes[index], str(node.get_meta("v044_path", "")), str(extras.get("module", "")))
			if original == null or node.mesh != original: fail("Static correction no longer uses its canonical GLB geometry"); return
			for surface: int in original.get_surface_count():
				var arrays := original.surface_get_arrays(surface)
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
				if vertices.is_empty() or normals.size() != vertices.size(): fail("Prepared mesh lost geometry/normals"); return
				for normal: Vector3 in normals:
					if not normal.is_finite() or normal.length_squared() < 0.5: fail("Prepared mesh has invalid normals"); return
			windows += int(window)
			covers += int(cover)
			checked += 1
	if windows != 8 or covers != 32: fail("Prepared reveal/bed-cover inventory changed"); return
	if checked==0:fail("No static corrections checked");return
	print("ESTATE_STATIC_PREPARATION checked=",checked," failures=0")
	source.free();quit()

func fail(message: String) -> void:
	push_error(message);quit(1)
