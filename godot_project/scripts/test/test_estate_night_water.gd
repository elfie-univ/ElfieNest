extends SceneTree
## The original fountain water glows; rings illuminate strictly inside-out.
func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var source := load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate() as Node3D
	root.add_child(source)
	load("res://rooms/estate/estate_water.gd").attach(source)
	var original_meshes := source.find_children("*","MeshInstance3D",true,false).size()
	var candidate: Node3D = load("res://runtime/lab/estate_water_candidates.gd").new()
	root.add_child(candidate)
	candidate.call("bind",source,Environment.new())
	candidate.call("sample",0.55,true)
	if not _require(candidate.get_node_or_null("LowFountainFan")==null,"Rejected fan light geometry still exists"):return
	var lake := candidate.get("lake") as MeshInstance3D
	var lake_material := lake.get_active_material(0) as ShaderMaterial
	if not _require(float(lake_material.get_shader_parameter("accent_strength"))>0.0 and float(lake_material.get_shader_parameter("accent_strength"))<0.2,"Evening lake accent is absent or overwhelms the water"):return
	if not _require(not lake_material.shader.code.contains("night_band_strength"),"Rejected lake stripe shader remains"):return
	var rings: Array = candidate.get("fountain_rings")
	if not _require(rings.size()==5,"Need the five original pool rings, not newly generated rings"):return
	for index in range(rings.size()):
		if index>0 and not _require(float(rings[index]["radius"])>float(rings[index-1]["radius"]),"Ring order is not based on real radii"):return
		candidate.call("sample",0.55+float(index)*0.7,true)
		var active := rings[index]["material"] as ShaderMaterial
		var energy := float(active.get_shader_parameter("accent_strength"))
		if not _require(energy>1.0,"Ring never visibly illuminates"):return
		for other in range(rings.size()):
			if other==index:continue
			if not _require(energy>float((rings[other]["material"] as ShaderMaterial).get_shader_parameter("accent_strength")),"Rings do not illuminate sequentially inside-out"):return
	var jets := 0
	for material: ShaderMaterial in candidate.get("fountain_materials"):
		if material.get_meta("estate_water_role", "")=="jet":
			jets+=1
			if not _require(float(material.get_shader_parameter("accent_strength"))>=1.0,"Original water jets are not illuminated"):return
	if not _require(jets==10,"Original pool jets changed"):return
	candidate.call("sample",9.0,false)
	for material: ShaderMaterial in candidate.get("fountain_materials"):
		if not _require(is_zero_approx(float(material.get_shader_parameter("accent_strength"))),"Daytime retained fountain emission"):return
	if not _require(candidate.find_children("*","MeshInstance3D",true,false).is_empty() and source.find_children("*","MeshInstance3D",true,false).size()==original_meshes,"Fountain candidate added/replaced authored geometry"):return
	print("PASS original ten jets glow, five real-radius rings pulse inside-out, no fan or lake stripes, no geometry changes, daytime off; visual approval pending")
	source.free()
	candidate.free()
	quit(0)

func _require(ok: bool,message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok
