extends SceneTree

var failures: Array[String] = []
func check(ok: bool, message: String) -> void:
 if not ok and not failures.has(message): failures.append(message); push_error(message)
func _initialize() -> void: call_deferred("run")
func run() -> void:
 var path := "res://nest/courtyard/parts/waterside/fountain_score.gd"
 if not ResourceLoader.exists(path):
  push_error("The approved nine-nozzle fountain score is missing")
  quit(1)
  return
 var score = load(path)
 for i in range(800):
  var t:=float(i)*0.1
  var state:Array=score.sample(t)
  check(state.size()==9,"Nine fixed nozzle positions")
  for j in range(9):
   check(state[j].height>=0.0 and state[j].height<=6.0,"Bounded water heights")
   check(is_equal_approx(state[j].height,score.sample(t+80.0)[j].height),"Seamless eighty-second cycle")
 check(score.sample(8.0)[0].flower_height>3.3 and score.sample(8.0)[0].height==0.0,"Opening flower phrase")
 check(score.sample(24.0)[0].flower_height>4.4,"Middle flower stays around 4.6 metres")
 check(score.sample(46.0)[0].height>5.8 and score.sample(46.0)[0].flower_height==0.0,"Six metre main plume climax")
 check(score.sample(62.0)[0].flower_height>5.8 and score.sample(62.0)[0].height==0.0,"Separate six metre flower climax")
 for t in [8.0,24.0,62.0,74.0]:
  check(score.sample(t)[1].get("inward",-1.0)==0.0,"Flower is accompanied by vertical outer jets")
 for t in [38.0,46.0]:
  check(score.sample(t)[1].get("inward",-1.0)==1.0,"Main plume is accompanied by inward arches")
 for t in [0.0,16.0,28.0,32.0,40.0,50.0,54.0,66.0,80.0]:
  var left:Array=score.sample(t-0.001)
  var right:Array=score.sample(t+0.001)
  for j in range(9): check(absf(left[j].height-right[j].height)<0.02,"Continuous pressure at phrase boundaries")
 var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
 root.add_child(estate)
 var display := preload("res://nest/courtyard/parts/waterside/estate_water_display.gd").new()
 root.add_child(display)
 display.fountain_programme="fixed"
 display.bind(estate)
 var show: Node3D=display.fountain_show
 var pool:=estate.find_child("Reference fountain water",true,false) as MeshInstance3D
 var channel:=estate.find_child("COMPLETE Short east spillway",true,false) as MeshInstance3D
 for water:MeshInstance3D in [pool,channel]:
  check(water.get_active_material(0).get_shader_parameter("fountain_waves")==true,"Expanding waves must reach both pool and channel water")
 display.sample(62.0,true)
 check(pool.get_active_material(0).get_shader_parameter("flower_reach")!=null,"Landing ripples follow the actual flower reach")
 check(show._drop_material.get_shader_parameter("impact_count")==17,"All seventeen possible landing regions have splash particles")
 check(show.jets.size()==9 and show.lenses.size()==9,"Nine independently lit nozzles")
 check(show.drops.multimesh.instance_count==2304,"Bounded shared spray batch replaces sparse isolated drops")
 check(show.ring_radius>=3.975 and show.ring_radius<4.2,"Place the outer nozzles at or beyond the last authored ripple, roughly fifty percent further out")
 for i in range(1,9):
  var origin:Vector3=show.jets[i].position
  check(absf(Vector2(origin.x,origin.z).length()-show.ring_radius)<0.001,"All outer nozzles share the outer ring")
  var angle:=atan2(origin.z,origin.x)
  check(absf(wrapf(angle-show.outlet_angle,-PI,PI))>=PI/8.0-0.001,"The spillway direction must bisect the gap between two nozzles")
 check(is_equal_approx(float(show._drop_material.get_shader_parameter("ring_radius")),show.ring_radius),"Drops and nozzles share the outer ring")

 check(show.central_jets.size()==8,"Eight flower arcs around the central plume")
 check(show.jets[0].get_active_material(0).get_shader_parameter("show_jet")==true,"The centre needs its own upward main plume")
 check(float(show.jets[0].get_active_material(0).get_shader_parameter("jet_radius"))>float(show.jets[1].get_active_material(0).get_shader_parameter("jet_radius"))*1.5,"Main plume must be thicker than the outer bubbling jets")
 check(float(show.jets[1].get_active_material(0).get_shader_parameter("jet_radius"))>=0.07,"Outer vertical columns must be visibly thick")
 var shared: Mesh=show.jets[0].mesh
 for jet: MeshInstance3D in show.jets: check(jet.mesh==shared,"All jets reuse one authored mesh")
 display.sample(4.0,true)
 check(display._lamp.light_energy>=0.6,"Flower-only state keeps the central light on")
 check(float(show.central_jets[0].material.get_shader_parameter("accent_strength"))>=1.4,"Night flower retains readable base emission")
 check(show.visibility_bounds.end.y>6.0,"Visibility bounds cover the taller climax")
 display.sample(62.0,true)
 check(float(show.central_jets[0].material.get_shader_parameter("jet_height"))>5.8,"Six metre flower reaches the GPU")
 check(float(show.central_jets[0].material.get_shader_parameter("flower_reach"))<show.ring_radius-0.5,"Flower landing leaves clearance inside outer jets")
 check(show.central_jets[0].material.get_shader_parameter("accent_color")!=show.jets[0].material_override.get_shader_parameter("accent_color"),"Main and flower use independent GPU colours")
 display.sample(23.0,true)
 check(show.jets[1].get_active_material(0).get_shader_parameter("jet_height") != show.jets[2].get_active_material(0).get_shader_parameter("jet_height"),"Actual GPU heights differ by group")
 check(show.lenses[1].get_active_material(0).emission_energy_multiplier != show.lenses[2].get_active_material(0).emission_energy_multiplier,"Nozzle lamps follow their own water pressure")
 display.sample(46.0,true)
 check(show.jets[1].material_override.get_shader_parameter("inward_mix")==1.0,"Outer arch orientation reaches the GPU")
 var inner_impacts:PackedVector4Array=pool.get_active_material(0).get_shader_parameter("impacts")
 check(inner_impacts.size()==17,"All water modes share landing regions")
 check(Vector2(inner_impacts[1].x,inner_impacts[1].y).length()<0.8,"Inward arches land near the main plume")
 check(inner_impacts[0].w>0.9 and inner_impacts[9].w==0.0,"Inactive flower landings do not emit foam")
 display.sample(62.0,false)
 var outer_impacts:PackedVector4Array=pool.get_active_material(0).get_shader_parameter("impacts")
 check(absf(Vector2(outer_impacts[1].x,outer_impacts[1].y).length()-show.ring_radius)<0.001,"Vertical outer spray returns to its nozzle landing")
 check(outer_impacts[0].w==0.0 and outer_impacts[9].w>0.9,"Flower-only impacts match active water")
 show.random_programme=true
 show.programme_seed=42
 for slot in range(16):
  display.sample(float(slot)*24.0+10.0,true)
  var landing:PackedVector4Array=pool.get_active_material(0).get_shader_parameter("impacts")
  for i in range(1,9):
   var material:ShaderMaterial=show.jets[i].material_override
   var height:float=material.get_shader_parameter("jet_height")
   check(height<=4.001,"Random programme reaches GPU within four metres")
   var inward:float=material.get_shader_parameter("inward_mix")
   var gpu_inwards:PackedFloat32Array=show._drop_material.get_shader_parameter("inwards")
   check(is_equal_approx(gpu_inwards[i],inward),"Each droplet group follows its own nozzle direction")
   check(absf(Vector2(landing[i].x,landing[i].y).length()-(show.ring_radius-(show.ring_radius-0.75)*inward))<0.001,"Mixed directions share exact GPU landing positions")
   check(is_equal_approx(landing[i].w,clampf(height/0.5,0.0,1.0)),"Random landing foam follows each active jet")
   if height<0.001:
    check(show.lenses[i].get_active_material(0).emission_energy_multiplier==0.0,"Idle chase nozzles do not glow")
  var petal_heights:PackedFloat32Array=show._drop_material.get_shader_parameter("flower_heights")
  for i in range(8):
   check(is_equal_approx(petal_heights[i],show.central_jets[i].material.get_shader_parameter("jet_height")),"Petal pressure reaches both water mesh and droplets")
 check(show.drops.multimesh.instance_count==2304,"Random choreography keeps the same particle ceiling")
 var camera:=Camera3D.new();root.add_child(camera);camera.current=true
 camera.global_position=show.global_position+Vector3(0,8,14);camera.look_at(show.global_position+Vector3.UP)
 display.refresh_visibility()
 check(display.is_processing(),"Visible fountain runs")
 var visible_time: float=display.presentation_seconds()
 var wall_start:=Time.get_ticks_msec()
 camera.look_at(camera.global_position+Vector3.FORWARD)
 camera.rotate_y(PI)
 display.refresh_visibility()
 check(not display.is_processing(),"Camera facing away stops animation updates")
 check(not display._lamp.visible,"Hidden fountain disables its local light")
 var count: int=show.sample_count
 await create_timer(0.12).timeout
 check(show.sample_count==count,"Offscreen frames perform no fountain samples")
 camera.look_at(show.global_position+Vector3.UP);display.refresh_visibility()
 check(absf(display.presentation_seconds()-visible_time-float(Time.get_ticks_msec()-wall_start)/1000.0)<0.01,"Return skips actual elapsed invisible time without replay")
 var blocker:=StaticBody3D.new();var collider:=CollisionShape3D.new();var box:=BoxShape3D.new();box.size=Vector3(6,20,0.3);collider.shape=box;blocker.add_child(collider);root.add_child(blocker);blocker.global_position=show.global_position+Vector3(0,4,7)
 await physics_frame
 await physics_frame
 display.refresh_visibility()
 check(not show.visible_from(camera) and display.is_processing(),"An exposed waterfall must keep running when only the fountain is occluded")
 box.size=Vector3(20,20,0.3)
 await physics_frame
 await physics_frame
 display.refresh_visibility()
 check(not display.is_processing(),"Opaque walls stop both occluded fountain and waterfall work")
 blocker.free();await physics_frame
 display.refresh_visibility()
 check(display.is_processing(),"Removing occlusion restores animation")
 display.set_presentation_paused(true)
 var frozen_time:float=display.presentation_seconds()
 count=show.sample_count
 await create_timer(0.12).timeout
 check(show.sample_count==count and not display.is_processing() and display.presentation_seconds()==frozen_time,"Monitor pause freezes work and show time")
 display.set_presentation_paused(false)
 display.sample(9.0,false)
 for lens: MeshInstance3D in show.lenses: check(is_zero_approx((lens.get_active_material(0) as BaseMaterial3D).emission_energy_multiplier),"No daytime glow")
 check(display.find_children("*","Light3D",true,false).size()==1,"Reuse one shadowless local light")
 print("FOUNTAIN_CHECKS failures=",failures.size()," jets=",show.jets.size()," drops=",show.drops.multimesh.instance_count)
 estate.free();display.free();camera.free()
 quit(0 if failures.is_empty() else 1)
