extends Node3D
## Seven local presentation layers. No transport command or resident mutation.
const BODY := preload("res://characters/tovren/tovren.tscn")
const COLUMN := preload("res://runtime/lab/estate_transit_column.gdshader")
const RING_COLORS := [Color(0.24,0.82,1.0),Color(0.65,0.42,1.0),Color(1.0,0.72,0.30)]
const ROOF_TURN_SECONDS := 2.4
const PETAL_START := 3.0 # Preparation only lights the apparatus; charge owns rotation.
const PETAL_TURN_SECONDS := 1.8
const PETAL_SPIN_END := 7.8
const UPLINK_START := 8.4
const DOME_SPREAD_START := 9.3
const DOME_PEAK := 10.6
const DOWN_SWEEP_START := 11.6
const DOWN_SWEEP_END := 13.4
const PREPARE_SECONDS := 11.7
const DESCENT_START := 3.0+PREPARE_SECONDS
const ARRIVAL_END := 7.0+PREPARE_SECONDS
const WALK_START := 8.0+PREPARE_SECONDS
const SETTLED_AT := 14.0+PREPARE_SECONDS
const REVIEW_END := 17.0+PREPARE_SECONDS
const CYCLE_SECONDS := 18.0+PREPARE_SECONDS
const IDLE_SECONDS := CYCLE_SECONDS-0.1

static func charge_turns(seconds: float) -> float:
	return 2.0*smoothstep(PETAL_START,PETAL_SPIN_END,seconds)

static func charge_angle(seconds: float) -> float:
	return fposmod(TAU*charge_turns(seconds),TAU)

static func stage_at(seconds: float) -> String:
	if seconds<PETAL_START: return "preparation"
	if seconds<DOWN_SWEEP_START: return "charge"
	if seconds<WALK_START: return "arrival"
	if seconds<SETTLED_AT: return "walk_down"
	return "settled"
var animation_stage := "empty"
var apparatus_seconds := ARRIVAL_END+2.0
var descent_rings: Array[MeshInstance3D] = []
var body_presence := 0.0
var stair_target := Vector3.ZERO
var standing_y := 0.0
var _effects: Node3D
var _body: ElfieActor
var _trace: MeshInstance3D
var _light: OmniLight3D
var _beam: MeshInstance3D
var _landing: MeshInstance3D
var _motes: MultiMeshInstance3D
var _update_apparatus: Callable
var _body_materials: Array[Dictionary] = []
var walk_profile: Array[Vector3] = []

func bind(effects: Node3D,platform_bounds: AABB,update_apparatus: Callable,stairs: Vector3=Vector3.ZERO,walking_surfaces: Array[MeshInstance3D]=[], existing_body: ElfieActor=null) -> void:
	_effects=effects
	_update_apparatus=update_apparatus
	global_position=effects.get_node("ArrivalEffect").global_position
	_body=existing_body if existing_body != null else BODY.instantiate() as ElfieActor
	if existing_body == null:
		_body.name="LocalPlatformBody"
		add_child(_body)
	_body.set_meta("local_visual_sample",true)
	_body.remove_from_group(&"runtime_elfie_actors")
	standing_y=platform_bounds.end.y+0.02
	_body.configure("local-platform-animation-fixture",Vector3(global_position.x,standing_y,global_position.z))
	_body.set_physics_process(false)
	(_body.get_node("CollisionShape3D") as CollisionShape3D).disabled=true
	(_body.get_node("NavigationAgent3D") as NavigationAgent3D).avoidance_enabled=false
	stair_target=stairs
	var facing := stairs
	facing.y=standing_y
	_body.look_at(facing,Vector3.UP,true)
	_build_walk_profile(walking_surfaces)
	for mesh: MeshInstance3D in _body.find_children("*","MeshInstance3D",true,false):
		if mesh.mesh==null:continue
		for surface in range(mesh.mesh.get_surface_count()):
			var source := mesh.get_active_material(surface) as BaseMaterial3D
			if source==null:continue
			var owned := source.duplicate() as BaseMaterial3D
			mesh.set_surface_override_material(surface,owned)
			_body_materials.append({"material":owned,"alpha":source.albedo_color.a,"transparency":source.transparency})
	for index in range(3):
		var ring := TorusMesh.new()
		ring.inner_radius=0.68+float(index)*0.23
		ring.outer_radius=ring.inner_radius+0.035
		var ring_node := _effect_mesh("TransitDirectionRing" if index==0 else "TransitColorRing%d" % index,ring,RING_COLORS[index])
		ring_node.scale.y=0.12
		descent_rings.append(ring_node)
	_trace=descent_rings[0]
	_beam=effects.get_node("ArrivalEffect/ArrivalBeam") as MeshInstance3D
	var column := CylinderMesh.new()
	column.height=2.9
	column.top_radius=1.22
	column.bottom_radius=1.22
	column.cap_top=false
	column.cap_bottom=false
	_beam.mesh=column
	_beam.position.y=1.45
	var veil := ShaderMaterial.new()
	veil.shader=COLUMN
	_beam.material_override=veil
	var landing_mesh := TorusMesh.new()
	landing_mesh.inner_radius=0.96
	landing_mesh.outer_radius=1.0
	_landing=_effect_mesh("LandingWave",landing_mesh,Color(0.3,0.8,1.0))
	_landing.scale.y=0.06
	_landing.position.y=0.02
	_motes=MultiMeshInstance3D.new()
	_motes.name="ArrivalMotes"
	var motes := MultiMesh.new()
	motes.transform_format=MultiMesh.TRANSFORM_3D
	var spark := SphereMesh.new()
	spark.radius=0.014
	spark.height=0.028
	spark.radial_segments=6
	spark.rings=3
	motes.mesh=spark
	motes.instance_count=36
	_motes.multimesh=motes
	_motes.material_override=_glow(Color(0.45,0.82,1.0))
	_motes.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_motes)
	_light=OmniLight3D.new()
	_light.name="LocalTransitLight"
	_light.omni_range=2.6
	_light.shadow_enabled=false
	_light.light_color=Color(0.28,0.75,1.0)
	_light.position.y=1.0
	add_child(_light)
	sample(0.0)

func sample(seconds: float) -> void:
	# Loop reset belongs only to this visual review. Adoption has no outbound leg.
	var time := fposmod(seconds,CYCLE_SECONDS)
	# Keep the accepted descent/walk motion after the longer charge sequence.
	var local := maxf(0.0,time-PREPARE_SECONDS) if time<ARRIVAL_END else 9.0
	if time<ARRIVAL_END:animation_stage="arrival"
	elif time<WALK_START:animation_stage="standing"
	elif time<SETTLED_AT:animation_stage="walk_down"
	else:animation_stage="settled"
	apparatus_seconds=time
	_update_apparatus.call(apparatus_seconds)
	_effects.call("preview_arrival",clampf(local*4.0/7.0,0.0,6.0))
	var progress := smoothstep(3.0,5.6,local)
	body_presence=progress if animation_stage=="arrival" else 1.0
	_body.global_position=Vector3(global_position.x,standing_y+(1.0-progress)*0.9,global_position.z)
	if time>=WALK_START:
		var distance := clampf((time-WALK_START)/6.0,0.0,1.0)*float(walk_profile.size()-1)
		var index := mini(int(distance),walk_profile.size()-2)
		_body.global_position=walk_profile[index].lerp(walk_profile[index+1],distance-float(index))
	_body.call("_play_animation","walking" if animation_stage=="walk_down" else "idle")
	(_body.get_node("AnimationPlayer") as AnimationPlayer).speed_scale=0.8 if animation_stage=="walk_down" else 1.0
	_body.visible=body_presence>0.001
	for binding: Dictionary in _body_materials:
		var material := binding["material"] as BaseMaterial3D
		material.transparency=int(binding["transparency"]) if body_presence>=0.999 else BaseMaterial3D.TRANSPARENCY_ALPHA
		material.albedo_color.a=float(binding["alpha"])*body_presence
	var level := smoothstep(1.7,2.8,local)*(1.0-smoothstep(5.8,7.0,local))
	_beam.visible=level>0.001
	(_beam.material_override as ShaderMaterial).set_shader_parameter("level",level)
	(_beam.material_override as ShaderMaterial).set_shader_parameter("seconds",local)
	(_beam.material_override as ShaderMaterial).set_shader_parameter("formation",smoothstep(1.7,2.8,local))
	for index in range(descent_rings.size()):
		var ring := descent_rings[index]
		var start := 2.7+float(index)*0.12
		var end := 5.5+float(index)*0.12
		var movement := smoothstep(start,end,local)
		ring.position.y=lerpf(2.65,0.08,movement)
		ring.visible=local>=start and local<end+0.4
		var fade := smoothstep(start,start+0.2,local)*(1.0-smoothstep(end,end+0.4,local))
		(ring.material_override as BaseMaterial3D).albedo_color.a=fade*0.72
	var landing := smoothstep(5.4,6.8,local)
	_landing.visible=local>=5.4 and local<6.8
	_landing.scale.x=lerpf(0.55,2.0,landing)
	_landing.scale.z=_landing.scale.x
	(_landing.material_override as BaseMaterial3D).albedo_color.a=(1.0-landing)*0.65
	_motes.visible=local>=2.8 and local<6.3
	for index in range(36):
		var phase := fposmod(float(index)*0.618,1.0)
		var angle := float(index)*2.399+local*0.65
		var radius := lerpf(1.1,0.25,progress)*(0.65+phase*0.35)
		var height := lerpf(2.6*phase,0.1+phase*0.3,progress)
		_motes.multimesh.set_instance_transform(index,Transform3D(Basis.IDENTITY,Vector3(cos(angle)*radius,height,sin(angle)*radius)))
	(_motes.material_override as BaseMaterial3D).albedo_color.a=(1.0-smoothstep(5.5,6.3,local))*0.75
	_light.visible=level>0.001
	_light.light_energy=level*0.4

func cancel() -> void:
	animation_stage="empty"
	apparatus_seconds=IDLE_SECONDS
	body_presence=0.0
	_body.visible=false
	_body.global_position.y=standing_y
	_beam.visible=false
	_landing.visible=false
	_motes.visible=false
	for ring: MeshInstance3D in descent_rings:ring.visible=false
	_light.visible=false
	_light.light_energy=0.0
	_effects.call("preview_arrival",9.0)
	_update_apparatus.call(apparatus_seconds)

func _effect_mesh(label: String,mesh: Mesh,color: Color) -> MeshInstance3D:
	var result := MeshInstance3D.new()
	result.name=label
	result.mesh=mesh
	result.material_override=_glow(color)
	result.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(result)
	return result

func _glow(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.transparency=BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color=Color(color,0.65)
	material.emission_enabled=true
	material.emission=color
	material.emission_energy_multiplier=0.5
	material.cull_mode=BaseMaterial3D.CULL_DISABLED
	return material

func _build_walk_profile(surfaces: Array[MeshInstance3D]) -> void:
	assert(not surfaces.is_empty(),"Walk-down review needs the real platform, steps and floor")
	var origin := Vector3(global_position.x,standing_y,global_position.z)
	var heading := stair_target-origin
	heading.y=0.0
	heading=heading.normalized()
	var side := heading.cross(Vector3.UP)
	var triangles := PackedVector3Array()
	for mesh: MeshInstance3D in surfaces:
		var faces := mesh.mesh.get_faces()
		for index in range(0,faces.size(),3):
			var a := mesh.to_global(faces[index])
			var b := mesh.to_global(faces[index+1])
			var c := mesh.to_global(faces[index+2])
			if absf((b-a).cross(c-a).y)<0.000001:continue
			var across := Vector3((a-origin).dot(side),(b-origin).dot(side),(c-origin).dot(side))
			if minf(across.x,minf(across.y,across.z))>0.01 or maxf(across.x,maxf(across.y,across.z)) < -0.01:continue
			triangles.append_array(PackedVector3Array([a,b,c]))
	for sample_index in range(67):
		var point := origin+heading*(3.3*float(sample_index)/66.0)
		var start := Vector3(point.x,standing_y+1.0,point.z)
		var top := -INF
		for index in range(0,triangles.size(),3):
			var hit: Variant = Geometry3D.ray_intersects_triangle(start,Vector3.DOWN,triangles[index],triangles[index+1],triangles[index+2])
			if hit!=null:top=maxf(top,(hit as Vector3).y)
		assert(is_finite(top),"Walk-down route lost an actual tread/floor surface")
		point.y=top+0.02
		walk_profile.append(point)
	print("ADOPTION_WALK_PROFILE ",walk_profile[0]," -> ",walk_profile.back()," samples=",walk_profile.size()," candidate_triangles=",triangles.size()/3)
