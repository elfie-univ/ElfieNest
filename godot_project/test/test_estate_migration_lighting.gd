extends SceneTree

const CONTROL := preload("res://nest/rendering/estate_lighting.gd")
const GEOMETRY := preload("res://tools/outdoor_lighting_geometry.gd")

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	create_timer(25.0).timeout.connect(func() -> void: quit(1))
	if not check_instance_buffers():
		quit(1)
		return
	if not await check_ground_rebuild():
		quit(1)
		return
	var world := Node3D.new()
	root.add_child(world)
	var ceiling := MeshInstance3D.new()
	ceiling.mesh = BoxMesh.new()
	ceiling.set_meta("extras", {"module":"central", "floor":3, "source_name":"ceiling ring perimeter diffuser"})
	var material := StandardMaterial3D.new()
	material.resource_name = "Warm ceiling bounce"
	material.emission_enabled = true
	material.emission_energy_multiplier = 0.5
	ceiling.mesh.material = material
	world.add_child(ceiling)
	if not require(CONTROL.lighting_group(ceiling) == &"central-03", "Ceiling rings are room lighting, not quiet-hour safety lighting"):
		return
	var control := CONTROL.new()
	control.bind(world)
	control.apply(false)
	var owned := ceiling.get_active_material(0) as BaseMaterial3D
	if not require(is_zero_approx(owned.emission_energy_multiplier), "Daytime must disable authored wall/ceiling emission too"):
		return
	control.apply(true)
	if not require(owned.emission_energy_multiplier > 0.0, "Evening must retain the original authored emission"):
		return
	control.apply(true, true)
	if not require(is_zero_approx(owned.emission_energy_multiplier), "Unoccupied room ceilings must switch off in quiet hours"):
		return
	var arrival := StandardMaterial3D.new()
	arrival.resource_name = "Roof fine turquoise halo"
	if not require(CONTROL.is_ordinary_emission(arrival), "Idle arrival fixtures must follow the day/quiet switch; event effects own their explicit activation"):
		return
	for file: String in ["res://nest/rendering/estate_opaque.gdshader", "res://nest/furniture/shared/bedroom/m01_sheen.gdshader"]:
		if not require(not FileAccess.get_file_as_string(file).contains("room_light_scale"), "Room surfaces must receive actual lights without the rejected fixed warm irradiance"):
			return
	var water := PackedVector2Array([Vector2(-2,-2),Vector2(2,-2),Vector2(2,2),Vector2(-2,2)])
	var geometry := GEOMETRY.new()
	var rim: PackedVector3Array = geometry.call("shoreline_rim", water, 0.2)
	if not require(rim.size() >= 5 and rim[0].is_equal_approx(rim[-1]), "Shoreline guidance must form a closed ring"):
		return
	for point in rim:
		if not require(not Geometry2D.is_point_in_polygon(Vector2(point.x, point.z), water), "The lake guidance emitter must sit on the bank, outside the water"):
			return
	world.free()
	print("PASS migrated day/evening/quiet lighting, actual-light receivers and bank-side lake guidance")
	quit(0)

func check_instance_buffers() -> bool:
	var library_root := Node3D.new()
	var prototype := MeshInstance3D.new()
	prototype.name = "Spray"
	prototype.mesh = SphereMesh.new()
	library_root.add_child(prototype)
	prototype.owner = library_root
	var packed := PackedScene.new()
	if not require(packed.pack(library_root) == OK, "Cannot build the batch fixture"): return false
	library_root.free()
	# Headless's dummy renderer does not retain per-instance GPU setter data.
	# Use the canonical 3x4 transforms and custom values stored by the asset.
	var buffer := PackedFloat32Array([
		1,0,0,1, 0,1,0,2, 0,0,1,3, 0.618034,0.2,0.3,1,
		1,0,0,2, 0,1,0,2, 0,0,1,3, 0.618034,0.2,0.3,1,
	])
	var binding := preload("res://nest/assembly/glb_placement.gd").new()
	binding.cached_libraries.clear()
	binding.library = packed
	binding.source_nodes = PackedStringArray(["Spray"])
	var target := MultiMeshInstance3D.new()
	binding.add_child(target)
	var data := {"transform_format":MultiMesh.TRANSFORM_3D,"use_colors":false,"use_custom_data":true,"instance_count":2,"visible_instance_count":-1,"custom_aabb":AABB(),"buffer":buffer}
	binding.instance_batches = {0:data}
	var valid := binding.bind_meshes()
	if not valid:
		binding.cached_libraries.clear()
		binding.free()
	if not require(valid, "Valid fountain instance data must bind without a lossless GPU readback"): return false
	if not require(target.multimesh.instance_count == 2 and target.multimesh.use_custom_data, "Batch binding changed instance count or format"): return false
	if not require(data.buffer.to_byte_array() == buffer.to_byte_array(), "Uploading instances changed their canonical source data"): return false
	data.buffer = PackedFloat32Array()
	var rejected := not binding.bind_meshes()
	binding.cached_libraries.clear()
	binding.free()
	if not require(rejected, "A nonempty batch must reject missing source data before upload"): return false
	print("BATCH_SOURCE_BUFFER_CHECK count=true source_preserved=true malformed_rejected=true")
	return true

func check_ground_rebuild() -> bool:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-10,0,0), Vector3(-9,0.2,0), Vector3(-9,0.7,1), Vector3(2,0.3,0), Vector3(3,0.5,0), Vector3(3,0.9,1)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP, Vector3.UP, Vector3.UP, Vector3.UP, Vector3.UP, Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.ONE,Vector2.ZERO,Vector2.RIGHT,Vector2.ONE])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2,3,4,5])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, StandardMaterial3D.new())
	var library_root := Node3D.new()
	var prototype := MeshInstance3D.new()
	prototype.name = "Ground"
	prototype.mesh = mesh
	prototype.set_meta("extras", {"nest_render_partition":{"cell_size":8.0,"surface_layers":[5]}})
	library_root.add_child(prototype)
	prototype.owner = library_root
	var packed := PackedScene.new()
	if not require(packed.pack(library_root) == OK, "Cannot build the ground fixture"): return false
	library_root.free()
	var binding := preload("res://nest/assembly/glb_placement.gd").new()
	binding.library = packed
	binding.source_nodes = PackedStringArray(["Ground"])
	var source := MeshInstance3D.new()
	source.layers = 5
	binding.add_child(source)
	source.owner = binding
	root.add_child(binding)
	var chunks := source.get_node_or_null("RenderChunks")
	if not require(chunks != null and chunks.get_child_count() == 2 and source.layers == 0, "The renderer must replace the original draw with spatial chunks"): return false
	if not require(chunk_faces(chunks) == face_keys(source.mesh), "Partitioning changed terrain height, normals, UVs or triangle multiplicity"): return false
	var identity := chunks.get_instance_id()
	binding.rebuild_render_partition(source)
	if not require(source.get_node("RenderChunks").get_instance_id() == identity, "Unchanged geometry must reuse its generated chunks"): return false
	var changed: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	changed[0].y = 1.2345
	arrays[Mesh.ARRAY_VERTEX] = changed
	source.mesh.clear_surfaces()
	source.mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	await process_frame
	await process_frame
	chunks = source.get_node("RenderChunks")
	if not require(chunks.get_instance_id() != identity and chunk_faces(chunks) == face_keys(source.mesh), "Changing source terrain must automatically rebuild the exact updated surface"): return false
	for chunk: Node in chunks.get_children():
		if not require(chunk.owner == null and (chunk as MeshInstance3D).layers == 5, "Generated chunks must remain unsaved and retain receiver layers"): return false
	var saved := PackedScene.new()
	if not require(saved.pack(binding) == OK, "Cannot round-trip the source binding"): return false
	var restored := saved.instantiate()
	if not require(restored.get_child(0).get_child_count() == 0, "Generated chunks leaked into a saved scene"): return false
	restored.free()
	binding.free()
	print("GROUND_AUTOMATIC_REBUILD_CHECK exact_surface=true changed_height=true no_saved_chunks=true")
	return true

func face_keys(mesh: Mesh) -> Dictionary:
	var keys := {}
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		for index: int in range(0, indices.size(), 3):
			var corners := []
			for offset: int in range(3):
				var vertex := indices[index+offset]
				corners.append([points[vertex], normals[vertex], uv[vertex]])
			var key := var_to_str(corners)
			keys[key] = int(keys.get(key, 0)) + 1
	return keys

func chunk_faces(chunks: Node) -> Dictionary:
	var result := {}
	for chunk: MeshInstance3D in chunks.get_children():
		var keys := face_keys(chunk.mesh)
		for key: String in keys: result[key] = int(result.get(key, 0)) + int(keys[key])
	return result
