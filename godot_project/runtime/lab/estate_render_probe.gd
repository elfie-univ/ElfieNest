extends Node
## Temporary opt-in measurement. Every diagnostic change is restored.
var nest: ModularNest
var viewport: Viewport
var groups := {}
var layers := {}
var lights := []
var original_scale := 1.0
var original_msaa := 0
var original_disable := false
var measuring := false

const GPU := """
(() => {
 const canvas=document.getElementById('canvas');
 const gl=canvas && canvas.getContext('webgl2');
 const ext=gl && gl.getExtension('EXT_disjoint_timer_query_webgl2');
 const info=gl && gl.getExtension('WEBGL_debug_renderer_info');
 const t={gl,ext,active:null,pending:[],samples:[],phase:'',disjoint:0,calls:{},counting:false,originals:{},mute:false};
 for(const name of ['drawElements','drawArrays','drawElementsInstanced','drawArraysInstanced','getBufferSubData','readPixels','bufferSubData','bufferData','getParameter','finish','clientWaitSync']){
   if(!gl || typeof gl[name]!=='function')continue;
   const original=gl[name];t.originals[name]=original;
   gl[name]=function(...args){if(t.mute && name.startsWith('draw'))return;if(!t.counting)return original.apply(this,args);
     const start=performance.now();const result=original.apply(this,args);
     const row=t.calls[name]??(t.calls[name]={calls:0,ms:0,max_ms:0});
     const elapsed=performance.now()-start;row.calls++;row.ms+=elapsed;row.max_ms=Math.max(row.max_ms,elapsed);return result;};
 }
 t.poll=()=>{if(!ext)return;
   const bad=gl.getParameter(ext.GPU_DISJOINT_EXT);
   if(bad)t.disjoint++;
   t.pending=t.pending.filter(p=>{
     if(!bad && !gl.getQueryParameter(p.query,gl.QUERY_RESULT_AVAILABLE))return true;
     if(!bad)t.samples.push({phase:p.phase,ms:gl.getQueryParameter(p.query,gl.QUERY_RESULT)/1e6});
     gl.deleteQuery(p.query);return false;
   });
 };
 t.begin=()=>{t.poll();if(!ext||t.active||t.pending.length>=8)return;
   if(gl.getQuery(ext.TIME_ELAPSED_EXT,gl.CURRENT_QUERY))return;
   const query=gl.createQuery();gl.beginQuery(ext.TIME_ELAPSED_EXT,query);
   t.active={query,phase:t.phase};
 };
 t.end=()=>{if(!t.active)return;gl.endQuery(ext.TIME_ELAPSED_EXT);
   t.pending.push(t.active);t.active=null;};
 t.take=()=>{t.poll();const samples=t.samples.filter(p=>p.phase===t.phase).map(p=>p.ms);
   return {supported:!!ext,samples_ms:samples,disjoint:t.disjoint};};
 window.__estateRenderTimer=t;
 console.log('ESTATE_GPU_CAPABILITY '+JSON.stringify({webgl:!!gl,timer:!!ext,
   renderer:info?gl.getParameter(info.UNMASKED_RENDERER_WEBGL):'',
   visibility:document.visibilityState}));
})();
"""

func category(node: GeometryInstance3D) -> String:
	var mesh: Mesh
	if node is MeshInstance3D: mesh = node.mesh
	elif node is MultiMeshInstance3D and node.multimesh != null: mesh = node.multimesh.mesh
	var source := str(mesh.get_meta("nest_source_library", "")) if mesh != null else ""
	if source.is_empty() and node.has_meta("source_geometry_path"):
		var owner := node.get_parent().get_parent() as MeshInstance3D
		if owner != null: source = str(owner.mesh.get_meta("nest_source_library", ""))
	for token: String in ["bed-shared", "bedroom-planters", "forest-foliage", "forest-wood", "tree-one", "plant-library", "central-building", "pod-building", "shared-ground"]:
		if source.contains(token): return token
	if source.contains("furniture/"): return "other-furniture"
	if source.contains("courtyard/"): return "other-courtyard"
	if source.contains("characters/") or not nest.is_ancestor_of(node): return "actors"
	return "other-runtime"

func begin_gpu() -> void:
	if OS.has_feature("web"): JavaScriptBridge.eval("window.__estateRenderTimer.begin()")

func end_gpu() -> void:
	if OS.has_feature("web"): JavaScriptBridge.eval("window.__estateRenderTimer.end()")

func quantile(values: Array, ratio: float) -> float:
	if values.is_empty(): return 0.0
	values.sort()
	return float(values[int((values.size()-1)*ratio)])

func measure(label: String, frames: int) -> void:
	JavaScriptBridge.eval("window.__estateRenderTimer.phase="+JSON.stringify(label))
	for i in range(4): await get_tree().process_frame
	var times := []; var cpu := []; var gpu := []; var setup := []
	var draws := []; var visible := []; var shadows := []; var primitives := []
	var previous := Time.get_ticks_usec()
	var rid := viewport.get_viewport_rid()
	for i in range(frames):
		await get_tree().process_frame
		var now := Time.get_ticks_usec()
		times.append((now-previous)/1000.0); previous = now
		cpu.append(RenderingServer.viewport_get_measured_render_time_cpu(rid))
		gpu.append(RenderingServer.viewport_get_measured_render_time_gpu(rid))
		setup.append(RenderingServer.get_frame_setup_time_cpu())
		draws.append(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		primitives.append(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
		visible.append(RenderingServer.viewport_get_render_info(rid,RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE,RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
		shadows.append(RenderingServer.viewport_get_render_info(rid,RenderingServer.VIEWPORT_RENDER_INFO_TYPE_SHADOW,RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME))
	var timer: Variant = JSON.parse_string(JavaScriptBridge.eval("JSON.stringify(window.__estateRenderTimer.take())"))
	print("ESTATE_RENDER_PHASE ",JSON.stringify({"phase":label,"frames":frames,"frame_p50_ms":quantile(times,0.5),"frame_p95_ms":quantile(times,0.95),"render_cpu_p50_ms":quantile(cpu,0.5),"render_gpu_p50_ms":quantile(gpu,0.5),"setup_cpu_p50_ms":quantile(setup,0.5),"draws":quantile(draws,0.5),"visible_draws":quantile(visible,0.5),"shadow_draws":quantile(shadows,0.5),"primitives":quantile(primitives,0.5),"timer":timer,"scale":viewport.scaling_3d_scale,"msaa":viewport.msaa_3d,"viewport":viewport.get_visible_rect().size}))

func run(world: ModularNest, characters: Node3D) -> void:
	nest = world; viewport = nest.get_viewport()
	original_scale = viewport.scaling_3d_scale; original_msaa = viewport.msaa_3d; original_disable = viewport.disable_3d
	await get_tree().create_timer(2.0).timeout
	for owner: Node in [nest,characters]:
		for node: GeometryInstance3D in owner.find_children("*","GeometryInstance3D",true,false):
			if not node.is_visible_in_tree() or node.layers == 0: continue
			var key := category(node)
			if not groups.has(key): groups[key] = []
			groups[key].append(node); layers[node] = node.layers
	for light: Light3D in nest.find_children("*","Light3D",true,false): lights.append({"node":light,"mask":light.light_cull_mask,"shadow":light.shadow_enabled})
	print("ESTATE_RENDER_INVENTORY ",JSON.stringify(groups.keys().map(func(key: String) -> Dictionary: return {"group":key,"nodes":groups[key].size()})))
	JavaScriptBridge.eval(GPU)
	RenderingServer.viewport_set_measure_render_time(viewport.get_viewport_rid(),true)
	RenderingServer.frame_pre_draw.connect(begin_gpu)
	RenderingServer.frame_post_draw.connect(end_gpu)
	measuring = true
	if bool(JavaScriptBridge.eval("new URLSearchParams(parent.location.search).get('render_probe') === 'compare'")):
		await compare(characters)
		return
	await measure("baseline",24)
	JavaScriptBridge.eval("window.__estateRenderTimer.calls={};window.__estateRenderTimer.counting=true")
	await measure("webgl_call_cost",8)
	JavaScriptBridge.eval("window.__estateRenderTimer.counting=false;console.log('ESTATE_WEBGL_CALL_COST '+JSON.stringify(window.__estateRenderTimer.calls))")
	viewport.scaling_3d_scale = original_scale*0.5
	await measure("quarter_pixels",16)
	viewport.scaling_3d_scale = original_scale
	viewport.msaa_3d = Viewport.MSAA_DISABLED
	await measure("msaa_off",16)
	viewport.msaa_3d = original_msaa
	for light: Dictionary in lights: light.node.shadow_enabled = false
	await measure("no_shadows",12)
	for light: Dictionary in lights: light.node.shadow_enabled = light.shadow
	for light: Dictionary in lights:
		if not light.node is DirectionalLight3D: light.node.light_cull_mask = 0
	await measure("no_local_lights",12)
	for light: Dictionary in lights: light.node.light_cull_mask = light.mask
	for key: String in groups:
		for node: GeometryInstance3D in groups[key]: node.layers = 0
		await measure("without/"+key,6)
		for node: GeometryInstance3D in groups[key]: node.layers = layers[node]
	await measure("restored",24)
	restore()
	print("ESTATE_RENDER_COMPLETE restored=true")

func compare(characters: Node3D) -> void:
	var batcher: Node = nest.get("_opaque_render_batches")
	var optics: RefCounted = nest.get("_observer_optics")
	var actor_process := {}
	for actor: Node in characters.get_children():
		actor_process[actor] = actor.is_processing()
		actor.set_process(false)
	var was_paused: bool = nest.get("_observer_presentation_paused")
	nest.set_observer_presentation_paused(true)
	batcher.set_enabled(false)
	optics.set_opaque_shared(false)
	await measure("unbatched_a",24)
	await RenderingServer.frame_post_draw
	var before := viewport.get_texture().get_image()
	optics.set_opaque_shared(true)
	batcher.set_enabled(true)
	await measure("batched_a",24)
	await RenderingServer.frame_post_draw
	var after := viewport.get_texture().get_image()
	var exact := before.get_data()==after.get_data()
	var metrics: Dictionary = {"exact":exact}
	if not exact and before.has_method("compute_image_metrics"): metrics.merge(before.call("compute_image_metrics",after,false))
	print("ESTATE_BATCH_IMAGE ",JSON.stringify(metrics))
	batcher.set_enabled(false)
	optics.set_opaque_shared(false)
	await measure("unbatched_b",24)
	optics.set_opaque_shared(true)
	batcher.set_enabled(true)
	await measure("batched_b",24)
	JavaScriptBridge.eval("window.__estateRenderTimer.mute=true")
	await measure("submission_without_gpu_draws",12)
	JavaScriptBridge.eval("window.__estateRenderTimer.mute=false")
	await measure("batched_restored",24)
	for actor: Node in actor_process: actor.set_process(actor_process[actor])
	nest.set_observer_presentation_paused(was_paused)
	restore()
	print("ESTATE_RENDER_COMPLETE restored=true")

func restore() -> void:
	if measuring:
		if OS.has_feature("web"): JavaScriptBridge.eval("if(window.__estateRenderTimer)window.__estateRenderTimer.mute=false")
		RenderingServer.frame_pre_draw.disconnect(begin_gpu)
		RenderingServer.frame_post_draw.disconnect(end_gpu)
		measuring = false
	for node: GeometryInstance3D in layers:
		if is_instance_valid(node): node.layers = layers[node]
	for light: Dictionary in lights:
		if is_instance_valid(light.node): light.node.light_cull_mask = light.mask; light.node.shadow_enabled = light.shadow
	if is_instance_valid(viewport):
		viewport.scaling_3d_scale = original_scale; viewport.msaa_3d = original_msaa; viewport.disable_3d = original_disable
		RenderingServer.viewport_set_measure_render_time(viewport.get_viewport_rid(),false)

func _exit_tree() -> void: restore()
