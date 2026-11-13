extends Node3D
## Reuse the authored tube topology and droplet mesh; animate only on screen.
const SCORE := preload("res://nest/courtyard/parts/waterside/fountain_score.gd")
const RANDOM_SCORE := preload("res://nest/courtyard/parts/waterside/fountain_random.gd")
const CYCLE := preload("res://nest/courtyard/parts/waterside/fountain_cycle.gd")
var programme := "fixed"
var _cycle := CYCLE.new()
var random_programme := false
var programme_seed := 20261102
var _random_score := RANDOM_SCORE.new()
const DROP_SHADER := preload("res://nest/courtyard/parts/waterside/fountain_drops.gdshader")
const DAYLIGHT := preload("res://nest/rendering/estate_daylight.gd")
var jets: Array[MeshInstance3D] = []
var central_jets: Array[Dictionary] = []
var lenses: Array[MeshInstance3D] = []
var drops: MultiMeshInstance3D
var sample_count := 0
var ring_radius := 0.0
var outlet_angle := 0.0
var _start_angle := 0.0
var _drop_material: ShaderMaterial
var _contents: Node3D
var visibility_bounds := AABB(Vector3(-4.2,-0.1,-4.2),Vector3(8.4,6.5,8.4))

func bind(source: Node3D,pool: MeshInstance3D,materials: Array[ShaderMaterial],outer_ripple_radius: float) -> void:
 var original: Array[MeshInstance3D] = []
 var central_fan: Array[MeshInstance3D] = []
 for mesh: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
  if mesh.get_meta("estate_water_preview_derivative",false): continue
  if str(mesh.name).begins_with("Animated reference central aerated jet "):
   central_fan.append(mesh)
   continue
  var material := mesh.get_active_material(0) as ShaderMaterial
  if material != null and material.get_meta("estate_water_role","")=="jet":
   var center := (mesh.global_transform*mesh.get_aabb()).get_center()
   var bounds := pool.global_transform*pool.get_aabb()
   if bounds.has_point(Vector3(center.x,bounds.get_center().y,center.z)): original.append(mesh)
 assert(original.size()==10,"Fountain score requires the ten authored central arc templates")
 var template := original[0]
 var water := template.get_active_material(0) as ShaderMaterial
 var bounds := pool.global_transform*pool.get_aabb()
 global_position=bounds.get_center()
 # Replace the seven rigid central reference strands with one rounded main plume.
 # Preserve source geometry; reuse its topology for eight pressure-shaped arcs.
 for old: MeshInstance3D in central_fan: old.visible=false
 for old: MeshInstance3D in original: old.visible=false
 # Reuse one authored arc at eight evenly spaced rotations about the pool centre.
 for i in range(8):
  var arc:=MeshInstance3D.new()
  arc.name="CentralFlower_%d"%i
  arc.mesh=template.mesh
  arc.layers=DAYLIGHT.WATER_LIGHT_LAYER
  arc.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
  add_child(arc)
  arc.custom_aabb=AABB(Vector3(-3.5,-0.1,-3.5),Vector3(7,6.5,7))
  var material:=water.duplicate() as ShaderMaterial
  arc.material_override=material
  material.set_shader_parameter("show_central",true)
  material.set_shader_parameter("flower_angle",float(i)*TAU/8.0)
  central_jets.append({"mesh":arc,"transform":arc.global_transform,"material":material})

 ring_radius=outer_ripple_radius+0.16
 var channel:=source.find_child("COMPLETE Short east spillway",true,false) as MeshInstance3D
 var outlet:Vector3=(channel.global_transform*channel.get_aabb()).get_center()-global_position
 outlet_angle=atan2(outlet.z,outlet.x)
 _start_angle=outlet_angle+PI/8.0
 visibility_bounds=AABB(Vector3(-ring_radius-0.25,-0.1,-ring_radius-0.25),Vector3((ring_radius+0.25)*2.0,6.5,(ring_radius+0.25)*2.0))
 _contents=Node3D.new();_contents.name="Nozzles";add_child(_contents)
 var lens_mesh:=CylinderMesh.new();lens_mesh.top_radius=0.075;lens_mesh.bottom_radius=0.075;lens_mesh.height=0.012;lens_mesh.radial_segments=12
 var rim_mesh:=CylinderMesh.new();rim_mesh.top_radius=0.105;rim_mesh.bottom_radius=0.105;rim_mesh.height=0.016;rim_mesh.radial_segments=12
 var metal:=StandardMaterial3D.new();metal.albedo_color=Color(0.17,0.19,0.17);metal.metallic=0.7;metal.roughness=0.35
 rim_mesh.material=metal
 for i in range(9):
  var angle:=_start_angle+float(i-1)*TAU/8.0
  var origin:=Vector3.ZERO if i==0 else Vector3(cos(angle),0,sin(angle))*ring_radius
  var jet:=MeshInstance3D.new();jet.name="CentralMainPlume" if i==0 else "OuterJet_%d"%i
  jet.mesh=template.mesh;jet.position=origin;jet.rotation.y=-angle
  jet.layers=DAYLIGHT.WATER_LIGHT_LAYER;jet.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
  jet.custom_aabb=AABB(Vector3(-4.3,-0.05,-0.6),Vector3(4.9,6.5,1.2))
  var material:=water.duplicate() as ShaderMaterial
  material.set_shader_parameter("show_central",false)
  material.set_shader_parameter("show_jet",true)
  material.set_shader_parameter("jet_radius",0.23 if i==0 else 0.115)
  material.set_shader_parameter("jet_seed",float(i)*1.73)
  jet.material_override=material;_contents.add_child(jet);jets.append(jet);materials.append(material)
  var housing:=MeshInstance3D.new();housing.name="NozzleHousing_%d"%i;housing.mesh=rim_mesh;housing.position=origin+Vector3(0,0.012,0);housing.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF;_contents.add_child(housing)
  var lens:=MeshInstance3D.new();lens.name="UnderwaterLamp_%d"%i;lens.mesh=lens_mesh;lens.position=origin+Vector3(0,0.026,0)
  var lamp_material:=StandardMaterial3D.new();lamp_material.albedo_color=Color(0.68,0.82,0.84);lamp_material.emission_enabled=true;lamp_material.shading_mode=BaseMaterial3D.SHADING_MODE_UNSHADED
  lens.material_override=lamp_material;lens.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF;_contents.add_child(lens);lenses.append(lens)
 var prototype := source.find_child("__ELFIE_INST_GROUP_133",true,false)
 assert(prototype != null,"Reuse the original droplet template")
 var drop_mesh: Mesh
 for node: MeshInstance3D in prototype.find_children("*","MeshInstance3D",true,false):
  drop_mesh=node.mesh
  break
 if prototype is MeshInstance3D: drop_mesh=prototype.mesh
 assert(drop_mesh != null)
 for batch: MultiMeshInstance3D in source.find_children("*","MultiMeshInstance3D",true,false):
  if batch.get_meta("source_group","")=="__ELFIE_INST_GROUP_133": batch.visible=false
 prototype.visible=false
 var instances:=MultiMesh.new();instances.transform_format=MultiMesh.TRANSFORM_3D;instances.use_custom_data=true;instances.mesh=drop_mesh;instances.instance_count=2304;instances.custom_aabb=visibility_bounds
 var drop_buffer:=PackedFloat32Array()
 for i in range(2304):
  drop_buffer.append_array(PackedFloat32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,fposmod(float(i)*0.618034,1.0),fposmod(float(i)*2.399963/TAU,1.0),float(i%7)/7.0]))
 # Keep a CPU buffer so headless PackedScene export retains every instance.
 instances.buffer=drop_buffer
 drops=MultiMeshInstance3D.new();drops.name="ReusedFountainDrops";drops.multimesh=instances;drops.layers=DAYLIGHT.WATER_LIGHT_LAYER;drops.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
 _drop_material=ShaderMaterial.new();_drop_material.shader=DROP_SHADER
 _drop_material.set_shader_parameter("impact_count",17)
 _drop_material.set_shader_parameter("ring_radius",ring_radius)
 _drop_material.set_shader_parameter("start_angle",_start_angle)
 _drop_material.set_shader_parameter("source_center",drop_mesh.get_aabb().get_center())
 _drop_material.set_shader_parameter("source_scale",0.065/maxf(drop_mesh.get_aabb().size.length(),0.001))
 drops.material_override=_drop_material;_contents.add_child(drops)

func sample(seconds: float,night: bool) -> Dictionary:
 sample_count+=1
 var state:=_cycle.sample(seconds,programme_seed) if programme=="auto" else (_random_score.sample(seconds,programme_seed) if random_programme else SCORE.sample(seconds))
 var heights:=PackedFloat32Array();var colors:=PackedColorArray()
 var central:Dictionary=state[0]
 var inwards:=PackedFloat32Array()
 var reach:=ring_radius-0.75
 var impacts:=PackedVector4Array()
 var impact_colors:=PackedColorArray()
 for i in range(17):
  var position:=Vector2.ZERO
  var radius:=0.65 if i==0 else 0.25
  var height:float=central.height
  var color:Color=central.color
  if i>0 and i<9:
   var angle:=_start_angle+float(i-1)*TAU/8.0
   position=Vector2(cos(angle),sin(angle))*(ring_radius-reach*float(state[i].inward))
   height=state[i].height
   color=state[i].color
  elif i>=9:
   var angle:=float(i-9)*TAU/8.0
   position=Vector2(cos(angle),sin(angle))*float(central.flower_reaches[i-9])
   height=central.flower_heights[i-9]
   color=central.flower_colors[i-9]
  impacts.append(Vector4(position.x,position.y,radius,clampf(height/0.5,0.0,1.0)))
  impact_colors.append(color)
 central["impacts"]=impacts
 central["impact_colors"]=impact_colors
 for i in range(central_jets.size()):
  var entry:Dictionary=central_jets[i]
  var material:=entry.material as ShaderMaterial
  material.set_shader_parameter("jet_height",central.flower_heights[i])
  material.set_shader_parameter("flower_reach",central.flower_reaches[i])
  var flower_color:Color=central.flower_colors[i]
  material.set_shader_parameter("water_pressure",clampf(central.flower_heights[i]/0.5,0.0,1.0))
  material.set_shader_parameter("show_time",seconds)
  material.set_shader_parameter("accent_color",Vector3(flower_color.r,flower_color.g,flower_color.b))
  material.set_shader_parameter("accent_strength",central.flower_energy if night else 0.0)

 for i in range(9):
  var entry: Dictionary=state[i]
  var material:=jets[i].material_override as ShaderMaterial
  material.set_shader_parameter("water_pressure",clampf(entry.height/0.5,0.0,1.0))
  material.set_shader_parameter("jet_height",entry.height)
  material.set_shader_parameter("inward_mix",0.0 if i==0 else entry.inward)
  material.set_shader_parameter("inward_reach",reach)
  material.set_shader_parameter("show_time",seconds)
  material.set_shader_parameter("accent_color",Vector3(entry.color.r,entry.color.g,entry.color.b))
  material.set_shader_parameter("accent_strength",entry.energy if night else 0.0)
  var lamp:=lenses[i].material_override as StandardMaterial3D
  lamp.emission=central.light_color if i==0 else entry.color;lamp.emission_energy_multiplier=(maxf(entry.energy,central.flower_energy) if i==0 else entry.energy) if night else 0.0
  lamp.albedo_color=entry.color if night else Color(0.43,0.55,0.57)
  heights.append(entry.height);colors.append(entry.color)
  inwards.append(0.0 if i==0 else entry.inward)
 _drop_material.set_shader_parameter("inwards",inwards)
 _drop_material.set_shader_parameter("inward_reach",reach)
 _drop_material.set_shader_parameter("impacts",impacts)
 _drop_material.set_shader_parameter("flower_heights",central.flower_heights)
 _drop_material.set_shader_parameter("flower_reaches",central.flower_reaches)
 _drop_material.set_shader_parameter("flower_colors",central.flower_colors)
 _drop_material.set_shader_parameter("heights",heights)
 _drop_material.set_shader_parameter("colors",colors)
 _drop_material.set_shader_parameter("show_time",seconds)
 var climax:float=central.climax
 drops.multimesh.visible_instance_count=1536+roundi(climax*768.0)
 _drop_material.set_shader_parameter("night_strength",0.35+climax*0.65 if night else 0.0)

 return state[0]

func set_detail(visible_now: bool,nearby: bool) -> void:
 _contents.visible=visible_now
 for entry: Dictionary in central_jets: (entry.mesh as MeshInstance3D).visible=visible_now
 drops.visible=nearby

func visible_from(camera: Camera3D) -> bool:
 var bounds:=global_transform*visibility_bounds
 for plane: Plane in camera.get_frustum():
  var nearest:=Vector3(bounds.position.x if plane.normal.x>=0 else bounds.end.x,bounds.position.y if plane.normal.y>=0 else bounds.end.y,bounds.position.z if plane.normal.z>=0 else bounds.end.z)
  if plane.distance_to(nearest)>0: return false
 # Sparse line-of-sight checks avoid animating behind an opaque room wall.
 var space:=get_world_3d().direct_space_state
 for offset: Vector3 in [Vector3(0,2.0,0),Vector3(ring_radius,1.2,0),Vector3(-ring_radius,1.2,0),Vector3(0,1.2,ring_radius),Vector3(0,1.2,-ring_radius)]:
  var query:=PhysicsRayQueryParameters3D.create(camera.global_position,global_position+offset,1)
  if space.intersect_ray(query).is_empty(): return true
 return false
