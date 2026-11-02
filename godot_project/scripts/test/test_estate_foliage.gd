extends SceneTree
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const OPTICS := preload("res://rooms/estate/estate_lighting_sample.gd")
func _initialize() -> void: call_deferred("run")
func run() -> void:
	var source: Node3D=load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(source)
	var estate := Node3D.new()
	root.add_child(estate)
	var originals: Dictionary={}
	for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		var selected := false
		for i in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(i)
			if "rubber tree" in material.resource_name.to_lower(): selected=true
		if selected or mesh.get_meta("extras",{}).get("coverage_role")=="plant":
			mesh.reparent(estate,true)
			if selected: originals[mesh]=mesh.mesh
	source.free()
	DAYLIGHT.apply(estate)
	var leaves := 0
	for mesh: MeshInstance3D in originals:
		assert(mesh.mesh==originals[mesh],"Foliage fix changed geometry")
		for surface in range(mesh.mesh.get_surface_count()):
			var original := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
			if "rubber tree" not in original.resource_name.to_lower(): continue
			var actual := mesh.get_active_material(surface) as ShaderMaterial
			if actual==null:
				push_error("Foliage still bypasses calibrated diffuse shading")
				quit(1)
				return
			assert(actual.get_shader_parameter("source_albedo")==original.albedo_color)
			assert(actual.get_shader_parameter("source_albedo_texture")==original.albedo_texture)
			if actual.get_shader_parameter("use_linear_vertex_color")!=true:
				push_error("Rubber tree lost authored vertex colors")
				quit(1)
				return
			leaves+=1
	assert(leaves>0)
	var sample := OPTICS.new()
	sample.bind_m01(estate)
	sample.apply_sample(1.0)
	var lamps := 0
	for light: Light3D in estate.find_children("*","Light3D",true,false):
		if str(light.name).begins_with("AuthoredDaylightFixture"):
			assert(not light.visible and is_zero_approx(light.light_energy),"Plant fixture is on in daylight")
			lamps+=1
	sample.apply_sample(0.0)
	for light: Light3D in estate.find_children("*","Light3D",true,false):
		if str(light.name).begins_with("AuthoredDaylightFixture"):
			assert(light.visible and light.light_color.r>light.light_color.b,"Plant fixture lost warm night illumination")
	assert(lamps>0)
	estate.free()
	print("PASS foliage: original vertex colors and geometry; plant lamps off by day and warm by night")
	quit()
