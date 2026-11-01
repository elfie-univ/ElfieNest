extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var shader_text:=FileAccess.get_file_as_string("res://rooms/estate/estate_opaque.gdshader")
	if "IRRADIANCE = vec4(mix(" in shader_text:
		push_error("Opaque surfaces still receive unmounted hemisphere irradiance")
		quit(1);return
	var raw: Node3D=load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(raw)
	preload("res://rooms/estate/estate_complete_final.gd")._place_lakeside_bench(raw)
	var bench: Dictionary={}
	for part: MeshInstance3D in raw.find_children("Lakeside*","MeshInstance3D",true,false):
		if "bench" in str(part.name) or str(part.name).begins_with("Lakeside back frame"):
			bench[str(part.name)]=part.global_transform
	raw.free()
	var estate: Node3D=load("res://rooms/estate/estate.tscn").instantiate()
	root.add_child(estate)
	var failures: Array[String]=[]
	if bench.size()!=9: failures.append("Missing bench seat, back, legs or frames")
	for part_name: String in bench:
		var part: Node3D=estate.get_node("CompleteFinal").find_child(part_name,true,false)
		if part==null or not part.global_transform.is_equal_approx(bench[part_name]):
			failures.append("Composed bench part did not move with the seat: "+part_name)
	var outdoor:=0
	var solar_sources:=0
	var lakeside_shadowed:=0
	var original_outdoor:=0
	for light: Light3D in estate.find_children("*","Light3D",true,false):
		if "ReferenceFill" in str(light.name) or "Hemisphere" in str(light.name): failures.append("Unmounted fill: "+str(light.name))
		if light is DirectionalLight3D:
			solar_sources+=1
			if not light.shadow_enabled: failures.append("Unshadowed directional compensation")
			if not is_equal_approx(light.light_energy,1.05/PI):failures.append("Sun energy still depends on removed ambient compensation")
		elif light.visible and light.get_meta("asset_role","")!="authored-daylight-fixture":
			failures.append("Source has no mounted fixture: "+str(light.name))
		if not light.visible or light is DirectionalLight3D: continue
		var owner_extras: Dictionary=light.get_parent().get_meta("extras",{})
		if light.get_meta("asset_role","")=="authored-daylight-fixture" and owner_extras.has("outdoor_fixture_id"):
			outdoor+=1
			var fixture_id:=str(owner_extras.outdoor_fixture_id)
			if fixture_id in ["H01","B01","B02"]:
				lakeside_shadowed+=1
				if not light.shadow_enabled or not (light.shadow_caster_mask & 16):failures.append("Lakeside source ignores landscape occlusion")
				if not is_equal_approx(light.shadow_bias,0.1) or not is_equal_approx(light.shadow_normal_bias,3.0):failures.append("Accepted lakeside shadow calibration changed")
			else:
				original_outdoor+=1
				if light.shadow_enabled:failures.append("Lakeside change enabled shadows on an unrelated fixture: "+fixture_id)
			if owner_extras.get("outdoor_fixture_id","") in ["B01","B02"]:
				for part: MeshInstance3D in light.get_parent().get_parent().find_children("*","MeshInstance3D",true,false):
					if part.layers & light.shadow_caster_mask:failures.append("Bollard source is trapped inside its own closed fixture")
					if part.cast_shadow==GeometryInstance3D.SHADOW_CASTING_SETTING_OFF:failures.append("Bollard must still cast shadows from other lights")
				if (light.shadow_caster_mask & 29)!=29:failures.append("Bollard must retain actor, ground, furniture and foliage occlusion")
	var daylight=preload("res://rooms/estate/estate_daylight.gd")
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		for surface in range(mesh.mesh.get_surface_count()):
			var material=mesh.get_active_material(surface)
			if material is BaseMaterial3D and daylight._is_authored_bounce(material.resource_name.to_lower()) and material.emission_enabled:
				failures.append("Painted surface emits without a fixture: "+material.resource_name)
	if outdoor!=42 or lakeside_shadowed!=3 or original_outdoor!=39:failures.append("Outdoor fixture inventory changed")
	if solar_sources!=2: failures.append("Only the two layer-separated views of the same sun are allowed")
	var reference: Node3D=load("res://rooms/nest.tscn").instantiate()
	var environment: Environment=(reference.get_node("WorldEnvironment") as WorldEnvironment).environment.duplicate(true)
	reference.free()
	var control=preload("res://rooms/estate/estate_lighting_sample.gd").new()
	control.bind_environment(environment)
	control.bind_m01(estate)
	control.apply_environment(0.0,true)
	if environment.ambient_light_energy!=0.0 or environment.ambient_light_source!=Environment.AMBIENT_SOURCE_DISABLED:
		failures.append("Review environment supplies unmounted ambient light")
	for light: DirectionalLight3D in estate.find_children("*","DirectionalLight3D",true,false):
		if light.visible and light.light_energy>0.0: failures.append("Night still receives solar/hemisphere light")
	for message in failures: push_error(message)
	print("ESTATE_LIGHT_SOURCES bench_parts=",bench.size()," lakeside_shadowed=",lakeside_shadowed," original_outdoor=",original_outdoor," failures=",failures.size())
	estate.free()
	quit(0 if failures.is_empty() else 1)
