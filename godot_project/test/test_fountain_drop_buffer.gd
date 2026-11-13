extends SceneTree
## Preserve native GLB render inputs and the real fountain batch on round-trip.

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	if not check_glb_materials() or not check_shared_bedding():
		quit(1)
		return
	var estate := (load("res://nest/assembly/estate.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(estate)
	var display := preload("res://nest/courtyard/parts/waterside/estate_water_display.gd").new()
	root.add_child(display)
	display.bind(estate)
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

func check_shared_bedding() -> bool:
	var model_path := "res://nest/furniture/shared/bedroom/bed-shared.glb"
	var local_parts := {}
	var desktop_ids := {}
	var ok := true
	for set_id: String in ["a", "b", "c", "d"]:
		var scene_path := "res://nest/furniture/sets/bedroom/bedroom-set-%s.scn" % set_id
		var bedroom := (load(scene_path) as PackedScene).instantiate() as Node3D
		root.add_child(bedroom)
		var bed := bedroom.get_node("bed-shared")
		var desktop := bedroom.get_node("desk-%s-local" % set_id)
		var shell := bed.get_child(0) as MeshInstance3D
		var inverse := shell.transform.affine_inverse()
		ok = ok and bed.library.resource_path == model_path and bed.source_nodes.size() == 132
		desktop_ids[desktop.source_nodes[0]] = true
		for i: int in bed.source_nodes.size():
			var part := bed.get_child(i) as MeshInstance3D
			var key: String = bed.source_nodes[i]
			var local := inverse * part.transform
			if set_id == "a":
				local_parts[key] = [part.mesh, local]
			else:
				ok = ok and local_parts.has(key) and part.mesh == local_parts[key][0]
				ok = ok and local.is_equal_approx(local_parts[key][1])
		bedroom.free()
	ok = ok and local_parts.size() == 132 and desktop_ids.size() == 4
	if not ok: push_error("A–D must place the same complete bed with distinct desktops")
	print("NEST_SHARED_BEDDING_CHECK ok=",ok)
	return ok
