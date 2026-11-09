extends SceneTree
## Preserve native GLB render inputs and the real fountain batch on round-trip.

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	if not check_glb_materials() or not check_bedding_normals():
		quit(1)
		return
	var estate := (load("res://nest/assembly/estate.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(estate)
	var display := preload("res://nest/estate/estate_water_display.gd").new()
	root.add_child(display)
	display.bind(estate,Environment.new(),false)
	var batch: MultiMesh = display.fountain_show.drops.multimesh
	var expected := PackedFloat32Array()
	for i: int in range(2304):
		expected.append_array(PackedFloat32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,fposmod(float(i)*0.618034,1.0),fposmod(float(i)*2.399963/TAU,1.0),float(i%7)/7.0]))
	var ok := batch.instance_count == 2304 and batch.buffer.to_byte_array() == expected.to_byte_array()
	var path := "res://../build/nest-comparison/fountain-drop-buffer.res"
	if ok:
		ok = ResourceSaver.save(batch,path,ResourceSaver.FLAG_COMPRESS) == OK
	if ok:
		var restored := ResourceLoader.load(path,"MultiMesh",ResourceLoader.CACHE_MODE_IGNORE) as MultiMesh
		ok = restored != null and restored.buffer.to_byte_array() == expected.to_byte_array()
	estate.free()
	display.free()
	if not ok: push_error("Fountain drop transforms/custom data were lost during headless capture or resource round-trip")
	print("FOUNTAIN_DROP_BUFFER_CHECK ok=",ok," floats=",expected.size())
	quit(0 if ok else 1)

func check_glb_materials() -> bool:
	var binder := preload("res://nest/assembly/glb_placement.gd").new()
	var path := "res://nest/furniture/shared/bedroom/bedroom-lamps.glb"
	binder.library = load(path)
	var meshes: Dictionary = binder.import_meshes(path)
	binder.free()
	var material: StandardMaterial3D = meshes["part_00000"].surface_get_material(0)
	var ok := material.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA and material.depth_draw_mode == BaseMaterial3D.DEPTH_DRAW_DISABLED and material.metallic_specular == 0.4674796760082245
	if not ok: push_error("GLB lamp lost native transparency, depth draw or specular settings")
	print("NEST_GLB_MATERIAL_CHECK ok=",ok," transparency=",material.transparency," depth=",material.depth_draw_mode," specular=",material.metallic_specular)
	return ok

func check_bedding_normals() -> bool:
	var binder := preload("res://nest/assembly/glb_placement.gd").new()
	var path := "res://nest/furniture/shared/bedroom/bed-shared.glb"
	binder.library = load(path)
	var meshes: Dictionary = binder.import_meshes(path)
	binder.free()
	var selected := preload("res://nest/assembly/glb_placement.gd").select_mesh(meshes,"part_00971","Generated/CompleteEstate/CompleteFinal/A | Throw | botanical diagonal folded linen2","M02")
	var ok: bool = selected != null and selected != meshes["part_00971"] and selected.resource_path.begins_with(path + "::")
	if ok:
		var arrays := selected.surface_get_arrays(0)
		var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var source := Vector3(0.522642493,0.462978780,-0.715887904)
		var found := false
		for index: int in positions.size():
			if positions[index].distance_to(Vector3(-0.306658387,0.369095266,0.624402046)) < 0.000001:
				found = true
				ok = ok and normals[index].angle_to(source) < 0.0002
		ok = ok and found
	if not ok: push_error("Room-specific bedding normals were not restored from the unique GLB")
	print("NEST_BEDDING_NORMAL_CHECK ok=",ok)
	return ok
