extends SceneTree

func _initialize() -> void:
	var scene := load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene
	var estate := scene.instantiate()
	var count := 0
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var label := str(mesh.name).replace("_", " ").to_lower()
		if "circular opal ceiling diffuser" not in label: continue
		count += 1
		var arrays := mesh.mesh.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var area := 0.0
		for index in range(0, indices.size(), 3):
			var a := vertices[indices[index]]
			var b := vertices[indices[index + 1]]
			var c := vertices[indices[index + 2]]
			area += (b - a).cross(c - a).length() * 0.5
		# Import compression quantizes vertices. Verify the full disc's area,
		# not an exactly-zero center coordinate in the packed mesh.
		print("IMPORTED_LAMP ", mesh.name, " luminous_area=", area)
		if absf(area - PI * 0.88 * 0.88) > 0.01:
			push_error("Imported main lamp must have a continuous solid luminous face: " + str(mesh.name))
			estate.free()
			quit(1)
			return
		var material := mesh.mesh.surface_get_material(0) as BaseMaterial3D
		if material == null or not material.emission_enabled:
			push_error("Main lamp face must retain its authored emission")
			estate.free()
			quit(1)
			return
	estate.free()
	if count != 3:
		push_error("Expected exactly three imported central ceiling lamps, got %d" % count)
		quit(1)
		return
	print("PASS three imported central lamps have solid emissive faces")
	quit(0)
