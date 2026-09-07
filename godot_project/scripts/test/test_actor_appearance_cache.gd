extends SceneTree

const ACTOR_APPEARANCE := preload("res://runtime/actor/actor_appearance.gd")
const DOG_SCENE := preload("res://characters/dog/dog.tscn")

var _actors: Array[Node] = []


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var first := DOG_SCENE.instantiate()
	_actors.append(first)
	root.add_child(first)
	await process_frame
	var first_visual := first.get_node("VisualRoot") as Node3D
	var first_collision := first.get_node("CollisionShape3D") as CollisionShape3D
	ACTOR_APPEARANCE.apply(
		first_visual,
		first_collision,
		{
			"height_scale": 1.0,
			"build_scale": 1.0,
			"material_parameters": {"palette_id": "silver_gray", "primary_color_id": "silver_gray"},
		},
		"dog",
	)
	var first_mesh := _processed_mesh(first_visual)
	if first_mesh == null:
		_fail("First dog apply produced no cached bind-position mesh")
		return
	var first_bind := _bind_positions(first_mesh)
	if first_bind.size() < 4 or not is_equal_approx(first_bind[3], 1.0):
		_fail("First dog cached mesh has no RGBA CUSTOM0 bind positions")
		return
	var first_shader := _appearance_shader(first_visual)
	if first_shader == null:
		_fail("First dog apply did not install the appearance shader")
		return

	var second := DOG_SCENE.instantiate()
	_actors.append(second)
	root.add_child(second)
	await process_frame
	var second_visual := second.get_node("VisualRoot") as Node3D
	var second_collision := second.get_node("CollisionShape3D") as CollisionShape3D
	var scale_before_reapply := first_visual.scale.y
	ACTOR_APPEARANCE.apply(
		second_visual,
		second_collision,
		{
			"height_scale": 1.15,
			"build_scale": 0.9,
			"material_parameters": {"palette_id": "silver_gray", "primary_color_id": "silver_gray"},
		},
		"dog",
	)
	var second_mesh := _processed_mesh(second_visual)
	if second_mesh == null:
		_fail("Second dog apply produced no cached bind-position mesh")
		return
	if second_mesh != first_mesh:
		_fail("Second dog actor rebuilt the bind-position mesh instead of sharing the cache")
		return
	if _bind_positions(second_mesh) != first_bind:
		_fail("Cached bind positions diverged between dog actors")
		return
	var second_shader := _appearance_shader(second_visual)
	if second_shader == null or second_shader != first_shader:
		_fail("Dog actors compiled separate appearance shaders instead of sharing one")
		return

	ACTOR_APPEARANCE.apply(
		first_visual,
		first_collision,
		{"height_scale": 0.85, "build_scale": 1.1},
		"dog",
	)
	if _processed_mesh(first_visual) != first_mesh:
		_fail("Re-applied appearance replaced the cached bind-position mesh")
		return
	if _bind_positions(first_mesh) != first_bind:
		_fail("Re-applied appearance changed the baked CUSTOM0 bind positions")
		return
	if not is_equal_approx(first_visual.scale.y, scale_before_reapply * 0.85):
		_fail("Re-applied appearance did not update the visual scale")
		return

	print(
		"ACTOR_APPEARANCE_CACHE: shared_mesh=true custom0_scale_independent=true entries=%d"
		% first_bind.size()
	)
	_cleanup()
	quit()


func _processed_mesh(visual_root: Node3D) -> ArrayMesh:
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var source_key := String(
			mesh_instance.get_meta(ACTOR_APPEARANCE.BIND_POSITION_SOURCE_META, "")
		)
		if source_key != "":
			return mesh_instance.mesh as ArrayMesh
	return null


func _bind_positions(mesh: ArrayMesh) -> PackedFloat32Array:
	var result := PackedFloat32Array()
	for surface_index in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface_index)
		if arrays.size() <= Mesh.ARRAY_CUSTOM0:
			continue
		var custom: Variant = arrays[Mesh.ARRAY_CUSTOM0]
		if custom is PackedFloat32Array and (custom as PackedFloat32Array).size() > result.size():
			result = custom as PackedFloat32Array
	return result


func _appearance_shader(visual_root: Node3D) -> Shader:
	for node in visual_root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := mesh_instance.get_surface_override_material(surface_index)
			if material is ShaderMaterial:
				return (material as ShaderMaterial).shader
	return null


func _cleanup() -> void:
	for actor in _actors:
		if is_instance_valid(actor):
			actor.free()


func _fail(message: String) -> void:
	push_error(message)
	_cleanup()
	quit(1)
