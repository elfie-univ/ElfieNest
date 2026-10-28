extends Node3D
## Local charge presentation; source asset, base, treads and physics stay intact.
const SIDE := preload("res://runtime/lab/estate_petal_side.gdshader")
const FLOW := preload("res://runtime/lab/estate_petal_flow.gdshader")
const TIMING := preload("res://runtime/lab/estate_platform_cycle.gd")
var shells: Array[Dictionary] = []
var rear_lights: Array[Dictionary] = []
var streams: Array[MeshInstance3D] = []
var core: MeshInstance3D
var dome: MeshInstance3D
var roof_blooms: Array[MeshInstance3D] = []
var uplink: MeshInstance3D
var downlink: MeshInstance3D
var down_front: MeshInstance3D
var stream_dimensions: Array[Vector2] = []
var column_height := 0.0
var carrier: MeshInstance3D
var rotation_angle := 0.0
var spin_turns := 0.0
var _moving: Array[Dictionary] = []
var _lamps: Array[Dictionary] = []
var _center := Vector3.ZERO
var _dome_y := 0.0

func bind(geometry: Node3D, lamps: Dictionary) -> void:
	var nodes := geometry.find_children("*","MeshInstance3D",true,false)
	for mesh: MeshInstance3D in nodes:
		if str((mesh.get_meta("extras",{}) as Dictionary).get("assembly",""))=="roof01_platform":
			var bounds := mesh.global_transform*mesh.get_aabb()
			_center=bounds.get_center()
			_center.y=bounds.end.y+0.025
	for mesh: MeshInstance3D in nodes:
		var assembly := str((mesh.get_meta("extras",{}) as Dictionary).get("assembly",""))
		if not assembly.begins_with("roof01_petal_"): continue
		_moving.append({"mesh":mesh,"rest":mesh.global_transform})
		if str(mesh.name).contains("single midrib outside"):
			preload("res://runtime/lab/estate_arrival_inlay.gd").install(mesh)
			var rear := ShaderMaterial.new()
			rear.shader=SIDE
			var bounds := mesh.global_transform*mesh.get_aabb()
			rear.set_shader_parameter("rear_line",true)
			rear.set_shader_parameter("bottom",bounds.position.y)
			rear.set_shader_parameter("height",bounds.size.y)
			mesh.material_override=rear
			mesh.visible=true
			rear_lights.append({"mesh":mesh,"material":rear})
			continue
		if str(mesh.name).contains("single midrib") or str(mesh.name).contains("luminous side return"):
			mesh.visible=false
		if not str(mesh.name).contains("shell and light channels"): continue
		var inlay := preload("res://runtime/lab/estate_arrival_inlay.gd").install(mesh)
		var bounds := mesh.global_transform*mesh.get_aabb()
		var material := ShaderMaterial.new()
		material.shader=SIDE
		material.set_shader_parameter("bottom",bounds.position.y)
		material.set_shader_parameter("height",bounds.size.y)
		# Keep the coating and its shader under the effect owner. Attaching an
		# overlay to a separately owned source mesh leaves teardown ordering
		# dependent on the fixture's geometry/material deletion sequence.
		var coating := MeshInstance3D.new()
		coating.name="LocalPetalSideCharge"
		coating.mesh=mesh.mesh
		coating.material_override=material
		coating.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(coating)
		coating.global_transform=mesh.global_transform
		_moving.append({"mesh":coating,"rest":coating.global_transform})
		var index := int(assembly.trim_prefix("roof01_petal_"))-1
		shells.append({"mesh":mesh,"coating":coating,"material":material,"inlay":inlay,"index":index})
		var start := bounds.get_center()
		var heading := Vector3(_center.x-start.x,0,_center.z-start.z).normalized()
		var across := Vector3(-heading.z,0,heading.x)
		var lo := INF
		var hi := -INF
		for vertex: Vector3 in mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
			var position := mesh.to_global(vertex).dot(across)
			lo=minf(lo,position); hi=maxf(hi,position)
		var width := hi-lo
		column_height=maxf(column_height,bounds.size.y)
		stream_dimensions.append(Vector2(width,bounds.size.y))
		streams.append(_stream(start,Vector3(_center.x,start.y,_center.z),width,bounds.size.y))
	for lamp: OmniLight3D in lamps.values():
		_lamps.append({"lamp":lamp,"rest":lamp.global_transform})
	# A narrow local carrier sits over the existing base; no source mesh is cut.
	var ring := TorusMesh.new()
	ring.inner_radius=2.20
	ring.outer_radius=2.26
	carrier=MeshInstance3D.new()
	carrier.name="LocalPetalInnerCarrier"
	carrier.mesh=ring
	carrier.scale.y=0.45
	add_child(carrier)
	carrier.global_position=_center
	var metal := StandardMaterial3D.new()
	metal.albedo_color=Color(0.15,0.23,0.27)
	metal.metallic=0.7
	metal.roughness=0.3
	ring.material=metal
	carrier.material_override=metal
	var pillar := CylinderMesh.new()
	pillar.height=column_height
	pillar.top_radius=1.05
	pillar.bottom_radius=1.05
	pillar.cap_top=false
	pillar.cap_bottom=false
	core=_effect("ConvergedArrivalCore",pillar)
	core.global_position=_center+Vector3.UP*column_height*0.5
	(core.material_override as ShaderMaterial).set_shader_parameter("core",true)
	(core.material_override as ShaderMaterial).set_shader_parameter("bottom",-column_height*0.5)
	(core.material_override as ShaderMaterial).set_shader_parameter("span",column_height)
	for mesh: MeshInstance3D in nodes:
		if str(mesh.name)!="Central integrated shallow skylight": continue
		dome=MeshInstance3D.new()
		dome.name="LocalDomeCharge"
		dome.mesh=mesh.mesh
		var material := ShaderMaterial.new()
		material.shader=preload("res://runtime/lab/estate_arrival_dome.gdshader")
		var bounds := mesh.global_transform*mesh.get_aabb()
		material.set_shader_parameter("center",bounds.get_center())
		material.set_shader_parameter("radius",maxf(bounds.size.x,bounds.size.z)*0.5)
		dome.material_override=material
		dome.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(dome)
		dome.global_transform=mesh.global_transform
		_dome_y=bounds.get_center().y
		var height := maxf(0.5,_dome_y-_center.y)
		var column := CylinderMesh.new()
		column.height=height
		column.top_radius=1.25
		column.bottom_radius=1.05
		column.cap_top=false
		column.cap_bottom=false
		uplink=_effect("CoreToDomeUplink",column)
		uplink.global_position=_center+Vector3.UP*height*0.5
		(uplink.material_override as ShaderMaterial).set_shader_parameter("uplink",true)
		(uplink.material_override as ShaderMaterial).set_shader_parameter("column_height",height)
		(uplink.material_override as ShaderMaterial).set_shader_parameter("bottom",-height*0.5)
		(uplink.material_override as ShaderMaterial).set_shader_parameter("span",height)
		var down_shape := column.duplicate() as CylinderMesh
		down_shape.bottom_radius=1.25
		downlink=_effect("DomeToPlatformSweep",down_shape)
		downlink.global_position=uplink.global_position
		(downlink.material_override as ShaderMaterial).set_shader_parameter("downlink",true)
		(downlink.material_override as ShaderMaterial).set_shader_parameter("column_height",height)
		(downlink.material_override as ShaderMaterial).set_shader_parameter("bottom",-height*0.5)
		(downlink.material_override as ShaderMaterial).set_shader_parameter("span",height)
		var disc := CylinderMesh.new()
		disc.height=0.035
		disc.top_radius=1.25
		disc.bottom_radius=1.25
		down_front=_effect("DescendingEnergyFront",disc)
		(down_front.material_override as ShaderMaterial).set_shader_parameter("front",true)
	# The shallow glass alone is partly hidden by the continuous upper cove.
	# Illuminate that actual ceiling surface too, with a height/normal mask so
	# the floor and lower surround keep their normal materials and brightness.
	for mesh: MeshInstance3D in nodes:
		if not str(mesh.name).begins_with("Central single continuous full-height envelope"): continue
		var roof := MeshInstance3D.new()
		roof.name="LocalFullCeilingBloom"
		roof.mesh=mesh.mesh
		roof.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var material := ShaderMaterial.new()
		material.shader=preload("res://runtime/lab/estate_arrival_dome.gdshader")
		var bounds := mesh.global_transform*mesh.get_aabb()
		var radius := maxf(bounds.size.x,bounds.size.z)*0.5
		material.set_shader_parameter("center",_center)
		material.set_shader_parameter("radius",radius)
		material.set_shader_parameter("roof_only",true)
		roof.material_override=material
		add_child(roof)
		roof.global_transform=mesh.global_transform
		roof_blooms.append(roof)
		(dome.material_override as ShaderMaterial).set_shader_parameter("center",_center)
		(dome.material_override as ShaderMaterial).set_shader_parameter("radius",radius)
	sample(0.0)

func sample(seconds: float) -> void:
	spin_turns=TIMING.charge_turns(seconds)
	# Count the unwrapped turns, then wrap only the visual transform. Two full
	# turns return home in the same direction; there is no reverse leg.
	rotation_angle=TIMING.charge_angle(seconds)
	var basis := Basis(Vector3.UP,-rotation_angle)
	var rotation := Transform3D(basis,_center-basis*_center)
	for item: Dictionary in _moving:
		(item["mesh"] as Node3D).global_transform=rotation*(item["rest"] as Transform3D)
	for item: Dictionary in _lamps:
		(item["lamp"] as Node3D).global_transform=rotation*(item["rest"] as Transform3D)
	carrier.rotation.y=-rotation_angle
	var clear := 1.0-smoothstep(TIMING.DESCENT_START,TIMING.ARRIVAL_END,seconds)
	var charge_clear := 1.0-smoothstep(TIMING.DOME_PEAK,TIMING.DOWN_SWEEP_START,seconds)
	var surge := exp(-pow((seconds-8.2)/0.18,2.0))
	for item: Dictionary in shells:
		var start := 1.35+float(item["index"])*0.2
		var fill := smoothstep(start,start+0.9,seconds)*clear
		var material := item["material"] as ShaderMaterial
		material.set_shader_parameter("fill",fill)
		var charge := 0.25+0.75*smoothstep(TIMING.PETAL_START,TIMING.PETAL_SPIN_END,seconds)
		var level := smoothstep(start,start+0.2,seconds)*clear*(charge+surge*0.4)
		material.set_shader_parameter("level",level)
		(item["inlay"] as ShaderMaterial).set_shader_parameter("fill",fill)
		(item["inlay"] as ShaderMaterial).set_shader_parameter("level",level*1.4)
	for index in range(rear_lights.size()):
		var material: ShaderMaterial=rear_lights[index]["material"]
		var start := 1.35+float(index)*0.2
		material.set_shader_parameter("fill",smoothstep(start,start+0.9,seconds)*clear)
		material.set_shader_parameter("level",smoothstep(start,start+0.2,seconds)*clear*0.65)
	var convergence := smoothstep(TIMING.PETAL_SPIN_END,TIMING.PETAL_SPIN_END+0.35,seconds)*charge_clear
	for index in range(streams.size()):
		var stream := streams[index]
		stream.global_transform=rotation
		stream.visible=convergence>0.001
		(stream.material_override as ShaderMaterial).set_shader_parameter("level",convergence)
		(stream.material_override as ShaderMaterial).set_shader_parameter("seconds",seconds-TIMING.PETAL_SPIN_END+float(index)*0.07)
	var accumulated := smoothstep(TIMING.PETAL_SPIN_END,TIMING.UPLINK_START,seconds)
	core.visible=accumulated*charge_clear>0.001
	core.scale=Vector3(lerpf(0.25,1.0,accumulated),1.0,lerpf(0.25,1.0,accumulated))
	(core.material_override as ShaderMaterial).set_shader_parameter("level",accumulated*charge_clear)
	(core.material_override as ShaderMaterial).set_shader_parameter("seconds",seconds)
	if dome!=null:
		var dome_clear := 1.0-smoothstep(TIMING.DOWN_SWEEP_START,TIMING.DOWN_SWEEP_END+0.5,seconds)
		var illumination := smoothstep(TIMING.DOME_SPREAD_START,TIMING.DOME_PEAK,seconds)*dome_clear
		dome.visible=illumination>0.001
		(dome.material_override as ShaderMaterial).set_shader_parameter("level",illumination)
		(dome.material_override as ShaderMaterial).set_shader_parameter("fill",smoothstep(TIMING.DOME_SPREAD_START,TIMING.DOME_PEAK,seconds)*1.1)
		(dome.material_override as ShaderMaterial).set_shader_parameter("seconds",seconds)
		for roof: MeshInstance3D in roof_blooms:
			roof.visible=dome.visible
			(roof.material_override as ShaderMaterial).set_shader_parameter("level",illumination)
			(roof.material_override as ShaderMaterial).set_shader_parameter("fill",smoothstep(TIMING.DOME_SPREAD_START,TIMING.DOME_PEAK,seconds)*1.1)
			(roof.material_override as ShaderMaterial).set_shader_parameter("seconds",seconds)
		var rise := smoothstep(TIMING.UPLINK_START,TIMING.DOME_SPREAD_START,seconds)
		uplink.visible=rise*charge_clear>0.001
		(uplink.material_override as ShaderMaterial).set_shader_parameter("level",rise*charge_clear)
		(uplink.material_override as ShaderMaterial).set_shader_parameter("rise",rise)
		(uplink.material_override as ShaderMaterial).set_shader_parameter("seconds",seconds)
		var sweep := smoothstep(TIMING.DOWN_SWEEP_START,TIMING.DOWN_SWEEP_END,seconds)
		var down_clear := 1.0-smoothstep(TIMING.DOWN_SWEEP_END,TIMING.DOWN_SWEEP_END+0.7,seconds)
		downlink.visible=seconds>TIMING.DOWN_SWEEP_START and down_clear>0.001
		down_front.visible=seconds>TIMING.DOWN_SWEEP_START and seconds<TIMING.DOWN_SWEEP_END
		down_front.global_position=Vector3(_center.x,lerpf(_dome_y,_center.y,sweep),_center.z)
		for mesh: MeshInstance3D in [downlink,down_front]:
			(mesh.material_override as ShaderMaterial).set_shader_parameter("level",down_clear)
			(mesh.material_override as ShaderMaterial).set_shader_parameter("rise",sweep)
			(mesh.material_override as ShaderMaterial).set_shader_parameter("seconds",seconds)

func _effect(label: String, shape: Mesh) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.name=label
	mesh.mesh=shape
	mesh.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := ShaderMaterial.new()
	material.shader=FLOW
	if shape is ArrayMesh: (shape as ArrayMesh).surface_set_material(0,material)
	else: (shape as PrimitiveMesh).material=material
	mesh.material_override=material
	add_child(mesh)
	return mesh

func _stream(start: Vector3, end: Vector3, width: float, height: float) -> MeshInstance3D:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	var tangent := (end-start).normalized()
	var side := tangent.cross(Vector3.UP).normalized()
	var rings: Array[PackedVector3Array] = []
	for index in range(25):
		var t := float(index)/24.0
		var point := start.lerp(end,t)
		var ring := PackedVector3Array()
		for slice in range(16):
			var angle := TAU*float(slice)/16.0
			ring.append(point+side*cos(angle)*width*0.5+Vector3.UP*sin(angle)*height*0.5)
		rings.append(ring)
	for index in range(24):
		for slice in range(16):
			var next := (slice+1)%16
			for vertex: Vector2i in [Vector2i(index,slice),Vector2i(index+1,slice),Vector2i(index+1,next),Vector2i(index,slice),Vector2i(index+1,next),Vector2i(index,next)]:
				var angle := TAU*float(vertex.y)/16.0
				tool.set_normal((side*cos(angle)/width+Vector3.UP*sin(angle)/height).normalized())
				tool.set_uv(Vector2(float(vertex.x)/24.0,float(vertex.y)/16.0))
				tool.add_vertex(rings[vertex.x][vertex.y])
	var result := _effect("PetalFullFaceVolume%d"%streams.size(),tool.commit())
	(result.material_override as ShaderMaterial).set_shader_parameter("bottom",start.y-height*0.5)
	(result.material_override as ShaderMaterial).set_shader_parameter("span",height)
	(result.material_override as ShaderMaterial).set_shader_parameter("color_phase",float(streams.size())/3.0)
	return result
