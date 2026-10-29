extends Node
## Opt-in measurements for the existing local tour, never a world authority.
var samples: Array = []
var elapsed := 0.0
var frames := 0
var frame_times: Array[float] = []
var clock := 0
var adapter := ""
var lights: Array[Node] = []
var latest: Dictionary = {}
var world: Node
var view_index := 0
var variant := 0
var tree_batches: Array = []
var tree_original: Mesh
var tree_candidate: ArrayMesh
var shell: MeshInstance3D
var shell_bias := 1.0
var sample_info: Dictionary = {}
var shadows_disabled := false
var day_display := false
var shadow_budget := false
var retina_budget := false
var sun_distances: Dictionary = {}
var shadow_lights: Array[Light3D] = []
func setup(source_world: Node) -> void:
	world=source_world
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(),true)
	adapter=RenderingServer.get_video_adapter_name()+" / "+RenderingServer.get_video_adapter_vendor()
	lights=world.find_children("*","Light3D",true,false)
	if OS.has_feature("web"):
		var info=str(JavaScriptBridge.eval("(()=>{try {const g=document.getElementById('canvas').getContext('webgl2');const e=g.getExtension('WEBGL_debug_renderer_info');return e?g.getParameter(e.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER);}catch(e){return 'unavailable'}})()"))
		adapter+=" / "+info
	for light: Light3D in lights:
		if light.shadow_enabled: shadow_lights.append(light)
		if light is DirectionalLight3D:
			sun_distances[light]=[light.directional_shadow_max_distance,light.directional_shadow_fade_start,light.directional_shadow_mode]
			if light.shadow_enabled: sample_info[str(light.name)]={"shadow_distance":light.directional_shadow_max_distance,"shadow_fade":light.directional_shadow_fade_start,"shadow_splits":2 if light.directional_shadow_mode==DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS else 4}
	day_display=not bool(world.get("_lights_on"))
	prepare_samples()
func prepare_samples() -> void:
	var estate=world.get_node("Generated/CompleteEstate")
	var prototype=estate.get_node("CompleteFinal").find_child("__ELFIE_INST_GROUP_020",true,false) as MeshInstance3D
	for batch: MultiMeshInstance3D in estate.find_children("*","MultiMeshInstance3D",false,false):
		if batch.get_meta("source_group","")=="__ELFIE_INST_GROUP_020":tree_batches.append(batch)
	if not tree_batches.is_empty():
		tree_original=tree_batches[0].multimesh.mesh
		var surfaces: Array=tree_original.get("_surfaces").duplicate()
		var imported: Array=prototype.mesh.get("_surfaces")
		var lods := 0
		for i in range(surfaces.size()):
			surfaces[i]=surfaces[i].duplicate()
			surfaces[i]["lods"]=[]
			lods+=imported[i].get("lods",[]).size()
		tree_candidate=ArrayMesh.new();tree_candidate.set("_surfaces",surfaces)
		tree_candidate.custom_aabb=(tree_original as ArrayMesh).custom_aabb
		tree_candidate.shadow_mesh=null # Reproduce the previous shadow path for this one group.
		sample_info["canopy_shadow_lod_records"]=lods
		sample_info["canopy_batches"]=tree_batches.size()
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		var e: Dictionary=mesh.get_meta("extras",{})
		if e.get("module","")=="M01" and e.get("source_name","")=="ROOM • sculpted continuous shell":
			shell=mesh;shell_bias=mesh.lod_bias;break
	sample_info["shell_found"]=shell!=null
func cycle_view() -> void:
	view_index=(view_index+1)%3
	var tour=get_parent()
	var camera: Camera3D=tour.camera
	if view_index==0:
		world.select_observer_camera_by_id("overview")
		tour.profile_camera_override=false;camera.make_current()
	elif view_index==1:
		tour.profile_camera_override=true
		world.select_observer_camera_by_id("dorm-01")
	else:
		tour.profile_camera_override=true;camera.make_current()
		camera.global_position=Vector3(-30.0,2.1,-10.0)
		camera.look_at(Vector3(-34.0,1.2,-14.0))
	reset_window()
func toggle_samples() -> void:
	variant=(variant+1)%4
	for batch: MultiMeshInstance3D in tree_batches:
		batch.multimesh.mesh=tree_candidate if variant in [1,3] else tree_original
		batch.lod_bias=1.0
	if shell!=null:shell.lod_bias=0.5 if variant in [2,3] else shell_bias
	reset_window()
func toggle_shadows() -> void:
	shadows_disabled=not shadows_disabled
	for light in shadow_lights: light.shadow_enabled=not shadows_disabled
	reset_window()
func toggle_shadow_budget() -> void:
	shadow_budget=not shadow_budget
	for light: DirectionalLight3D in sun_distances:
		light.directional_shadow_max_distance=minf(sun_distances[light][0],30.0) if shadow_budget else sun_distances[light][0]
		light.directional_shadow_fade_start=0.7 if shadow_budget else sun_distances[light][1]
		light.directional_shadow_mode=DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS if shadow_budget else sun_distances[light][2]
	reset_window()
func toggle_retina_budget() -> void:
	retina_budget=not retina_budget
	get_viewport().scaling_3d_scale=0.75 if retina_budget else 1.0
	reset_window()
func toggle_day() -> void:
	day_display=not day_display
	world.apply_environment_state("nest/environment",not day_display,false)
	reset_window()
func reset_window() -> void:
	elapsed=0;frames=0;frame_times.clear();clock=0
func status() -> String:
	return "F6 view: %s | F7: %s\nDraws %.0f | primitives %.0f"%[["Roof","M01","Forest"][view_index],["Fixed source","Previous canopy shadows","Shell sample","Previous shadows + shell"][variant],float(latest.get("draw_calls",0)),float(latest.get("primitives",0))]
func sample_frame() -> Dictionary:
	var now:=Time.get_ticks_usec()
	if clock==0:clock=now;return latest
	var seconds:=float(now-clock)/1000000.0;clock=now
	elapsed+=seconds;frames+=1;frame_times.append(seconds*1000.0)
	if elapsed<1.0:return latest
	var viewport:=get_viewport().get_viewport_rid()
	var visible_lights:=0
	for light in lights:
		if is_instance_valid(light) and light.is_visible_in_tree():visible_lights+=1
	var cpu:=RenderingServer.viewport_get_measured_render_time_cpu(viewport)
	var gpu:=RenderingServer.viewport_get_measured_render_time_gpu(viewport)
	latest={"view":["Roof","M01","Forest"][view_index],"variant":["Fixed source","Previous canopy shadows","Shell sample","Previous shadows + shell"][variant],"sample_info":sample_info,"shadows_disabled":shadows_disabled,"day_display":day_display,"shadow_budget":shadow_budget,"render_scale":get_viewport().scaling_3d_scale,"shadow_lights":shadow_lights.size(),"visible_draws":RenderingServer.viewport_get_render_info(viewport,RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME),"shadow_draws":RenderingServer.viewport_get_render_info(viewport,RenderingServer.VIEWPORT_RENDER_INFO_TYPE_SHADOW,RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME),"adapter":adapter,"fps":frames/elapsed,"frame_ms_p50":percentile(frame_times,.5),"frame_ms_p95":percentile(frame_times,.95),"render_cpu_ms":cpu if cpu>0 else null,"render_gpu_ms":gpu if gpu>0 else null,"process_ms":Performance.get_monitor(Performance.TIME_PROCESS)*1000.0,"physics_ms":Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)*1000.0,"draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),"primitives":Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),"render_objects":Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME),"visible_lights":visible_lights,"viewport":str(get_viewport().size),"time_scale":Engine.time_scale}
	samples.append(latest.duplicate());if samples.size()>90:samples.pop_front()
	elapsed=0.0;frames=0;frame_times.clear()
	if OS.has_feature("web"):
		var payload:=JSON.stringify({"latest":latest,"samples":samples})
		JavaScriptBridge.eval("(()=>{let e=document.getElementById('estate-performance');if(!e){e=document.createElement('script');e.id='estate-performance';e.type='application/json';document.body.appendChild(e)}e.textContent="+JSON.stringify(payload)+"})()")
	return latest
static func percentile(values: Array[float],fraction: float) -> float:
	if values.is_empty():return 0.0
	var ordered:=values.duplicate();ordered.sort()
	return ordered[clampi(ceili(fraction*ordered.size())-1,0,ordered.size()-1)]
