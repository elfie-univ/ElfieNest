extends Node3D
## One local arrival preview: original interior fixtures, owned materials.
const FIXTURE := preload("res://runtime/lab/estate_arrival_fixture.gdshader")
const TIMING := preload("res://runtime/lab/estate_platform_cycle.gd")
var bindings: Array[Dictionary] = []
var petal_lights: Dictionary = {}
var petal_charge: Node3D
var night := false
var stage := "settled"
var _center := Vector3.ZERO
var _guide_axis := Vector3.FORWARD
var _platform_top := 0.0

func bind(geometry: Node3D) -> void:
	var nodes := geometry.find_children("*","MeshInstance3D",true,false)
	var steps_center := Vector3.ZERO
	for mesh: MeshInstance3D in nodes:
		var assembly := str((mesh.get_meta("extras",{}) as Dictionary).get("assembly",""))
		if assembly=="roof01_platform":
			var bounds := mesh.global_transform*mesh.get_aabb()
			_center=bounds.get_center()
			_platform_top=bounds.end.y
		if assembly=="roof01_steps": steps_center=(mesh.global_transform*mesh.get_aabb()).get_center()
	_guide_axis=Vector3(steps_center.x-_center.x,0,steps_center.z-_center.z).normalized()
	for mesh: MeshInstance3D in nodes:
		if str(mesh.name).begins_with("Roof lighting upper perimeter cove flush diffuser"):
			_widen_interior_diffuser(mesh)
		if str(mesh.name)=="Central skylight soft luminous inset":
			var center := (mesh.global_transform*mesh.get_aabb()).get_center()
			mesh.scale.x*=3.63/3.45
			mesh.scale.z*=3.63/3.45
			mesh.global_position+=center-(mesh.global_transform*mesh.get_aabb()).get_center()+Vector3.DOWN*0.025
		var e := mesh.get_meta("extras",{}) as Dictionary
		if e.get("module")!="central" or int(e.get("floor",0))!=4:continue
		# These are large baked warm-light cards, not physical ring diffusers.
		# In the close review camera they can fill the frame like a colored sky.
		# Keep their source geometry, but exclude this local presentation overlay.
		if str(mesh.name).contains("soft adjacent illumination"):
			mesh.visible=false
			continue
		var assembly := str(e.get("assembly",""))
		var group := ""
		var delay := 0.0
		var tint := Color(0.22,0.8,1.0)
		if str(mesh.name)=="Central skylight soft luminous inset":group="top_1";delay=0.0
		elif assembly=="roof_integrated_ceiling_light":group="top_2";delay=0.55;tint=Color(0.62,0.46,1.0)
		elif assembly=="roof_lighting_upper_cove":group="top_3";delay=1.1;tint=Color(1.0,0.72,0.32)
		elif assembly.begins_with("roof01_petal_"):group="petal_"+assembly.trim_prefix("roof01_petal_");delay=1.35+float(int(assembly.trim_prefix("roof01_petal_"))-1)*0.2
		elif assembly=="roof01_platform":group="platform";delay=2.0
		elif assembly=="roof_integrated_inner_light":group="floor_inner";tint=Color(1.0,0.78,0.48)
		elif assembly=="roof_integrated_perimeter_light":group="floor_outer";tint=Color(1.0,0.78,0.48)
		elif assembly=="roof01_steps":group="steps";tint=Color(1.0,0.78,0.48)
		if group.is_empty():continue
		if group.begins_with("petal_") and str(mesh.name).contains("single midrib inside"):
			var lamp := OmniLight3D.new()
			lamp.name="ArrivalPetalCharge"+group.trim_prefix("petal_")
			lamp.light_color=Color(0.12,0.72,1.0)
			lamp.omni_range=1.25
			lamp.shadow_enabled=false
			add_child(lamp)
			var center := (mesh.global_transform*mesh.get_aabb()).get_center()
			var inward := Vector3(-center.x,0,-center.z).normalized()
			lamp.global_position=center+inward*0.18
			petal_lights[group]=lamp
		for surface in range(mesh.mesh.get_surface_count()):
			var source := mesh.mesh.surface_get_material(surface) as BaseMaterial3D
			if source==null or not source.emission_enabled:continue
			var assigned := group
			if group=="platform":
				assigned="platform_side" if source.resource_name.contains("soft warm-white concealed") else ("platform_ring" if source.resource_name.contains("cyan light channel") else "platform_disc")
			var material := _material(source.albedo_color,tint,assigned)
			var bounds := mesh.global_transform*mesh.get_aabb()
			material.set_shader_parameter("petal_bottom",bounds.position.y)
			material.set_shader_parameter("petal_height",maxf(bounds.size.y,0.05))
			material.set_shader_parameter("guide_enabled",assigned=="steps")
			material.set_shader_parameter("guide_axis",_guide_axis)
			material.set_shader_parameter("guide_origin",_center)
			material.set_shader_parameter("platform_ring",assigned=="platform_ring")
			material.set_shader_parameter("platform_top",_platform_top)
			var span := absf(_guide_axis.x)*bounds.size.x+absf(_guide_axis.z)*bounds.size.z
			material.set_shader_parameter("guide_min",(bounds.get_center()-_center).dot(_guide_axis)-span*0.5)
			material.set_shader_parameter("guide_span",maxf(span,0.01))
			if source.albedo_texture!=null:
				material.set_shader_parameter("use_source_texture",true)
				material.set_shader_parameter("source_texture",source.albedo_texture)
			if source.emission_texture!=null:
				material.set_shader_parameter("use_emission_texture",true)
				material.set_shader_parameter("emission_texture",source.emission_texture)
			mesh.set_surface_override_material(surface,material)
			var peak := 2.2 if assigned=="top_3" else (1.7 if assigned.begins_with("top_") else 0.85)
			bindings.append({"material":material,"source":source,"source_energy":source.emission_energy_multiplier,"source_albedo":source.albedo_color,"group":assigned,"delay":delay,"peak":peak})
	petal_charge=preload("res://runtime/lab/estate_petal_charge.gd").new()
	add_child(petal_charge)
	petal_charge.bind(geometry,petal_lights)
	sample(TIMING.IDLE_SECONDS)

func _widen_interior_diffuser(mesh: MeshInstance3D) -> void:
	# Widen the existing indoor cove face in an owned mesh; do not add an
	# exterior shell band or move the light away from its original mounting.
	var source := mesh.mesh
	var owned := ArrayMesh.new()
	for surface in range(source.get_surface_count()):
		var arrays := source.surface_get_arrays(surface).duplicate(true)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for index in range(vertices.size()):
			var point := mesh.to_global(vertices[index])
			var radius := Vector2(point.x,point.z).length()
			var target := 5.23+(radius-5.23)*2.75
			point.x*=target/radius
			point.z*=target/radius
			vertices[index]=mesh.to_local(point)
		arrays[Mesh.ARRAY_VERTEX]=vertices
		owned.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
		owned.surface_set_material(surface,source.surface_get_material(surface))
	mesh.mesh=owned

func _material(albedo: Color,tint: Color,group: String) -> ShaderMaterial:
	var result := ShaderMaterial.new()
	result.shader=FIXTURE
	result.set_shader_parameter("source_albedo",albedo)
	result.set_shader_parameter("light_tint",Vector3(tint.r,tint.g,tint.b))
	result.set_shader_parameter("chases",group.begins_with("top_") or group=="platform_ring")
	result.set_shader_parameter("petal",group.begins_with("petal_"))
	result.set_shader_parameter("turn_seconds",TIMING.ROOF_TURN_SECONDS)
	return result

func sample(seconds: float) -> void:
	stage=TIMING.stage_at(seconds)
	if petal_charge!=null: petal_charge.sample(seconds)
	var fade := 1.0-smoothstep(TIMING.DESCENT_START,TIMING.ARRIVAL_END,seconds)
	var charge := smoothstep(TIMING.PETAL_START,TIMING.PETAL_SPIN_END,seconds)
	var rotating := seconds>TIMING.PETAL_START and seconds<TIMING.PETAL_SPIN_END
	var after_walk := 1.0-smoothstep(TIMING.SETTLED_AT+0.3,TIMING.REVIEW_END-0.5,seconds)
	for binding: Dictionary in bindings:
		var group := str(binding["group"])
		var delay := float(binding["delay"])
		var ready := smoothstep(delay,delay+0.55,seconds)
		var steady := 0.08 if night else 0.0
		var extra := float(binding["peak"])*ready*(0.25+charge*0.75)*fade
		if group.begins_with("top_"):
			var ring_index := int(group.trim_prefix("top_"))-1
			var wave_start := TIMING.DOME_SPREAD_START+float(ring_index)*0.4
			var bloom := smoothstep(wave_start,wave_start+0.5,seconds)
			extra*=0.6+0.4*bloom
		var guide := 0.0
		if group=="platform_side": extra=ready*(0.06+charge*0.14)*fade
		elif group=="steps":
			guide=smoothstep(TIMING.WALK_START-0.8,TIMING.WALK_START-0.1,seconds)
			extra=guide*after_walk*0.65
		elif group=="floor_inner": extra=smoothstep(TIMING.WALK_START+3.6,TIMING.WALK_START+4.3,seconds)*after_walk*0.6
		elif group=="floor_outer": extra=smoothstep(TIMING.WALK_START+4.4,TIMING.WALK_START+5.1,seconds)*after_walk*0.55
		var level := steady+extra
		var material := binding["material"] as ShaderMaterial
		material.set_shader_parameter("light_level",level)
		material.set_shader_parameter("sequence_amount",1.0 if rotating else 0.0)
		material.set_shader_parameter("spin_angle",TIMING.charge_angle(seconds))
		material.set_shader_parameter("seconds",seconds)
		material.set_shader_parameter("guide_progress",guide)
		material.set_shader_parameter("converge",smoothstep(TIMING.PETAL_SPIN_END,TIMING.UPLINK_START,seconds)*fade if group in ["platform_ring","platform_disc"] else 0.0)
		if petal_lights.has(group):
			var lamp := petal_lights[group] as OmniLight3D
			lamp.visible=extra>0.001
			lamp.light_energy=0.25*extra
