extends Node
## Opt-in read-only counters for the actual rendered estate, not a test scene.
var elapsed := 0.0
var frames := 0
var samples := 0
var worst_frame_ms := 0.0
var last_usec := Time.get_ticks_usec()

func _process(_delta: float) -> void:
	var now := Time.get_ticks_usec()
	var delta := (now-last_usec)/1000000.0
	last_usec=now
	elapsed+=delta;frames+=1
	worst_frame_ms=maxf(worst_frame_ms,delta*1000.0)
	if elapsed<2.0:return
	var report := {
		"static_bytes":OS.get_static_memory_usage(),
		"static_peak_bytes":OS.get_static_memory_peak_usage(),
		"render_video_bytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
		"render_texture_bytes":Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED),
		"render_buffer_bytes":Performance.get_monitor(Performance.RENDER_BUFFER_MEM_USED),
		"nodes":get_tree().get_node_count(),
		"draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
		"primitives":Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
		"frame_ms_mean":elapsed*1000.0/frames,
		"frame_ms_max":worst_frame_ms,
		"sample":samples,
		"scope":"Rendered estate review; excludes full-world navigation/physics and actors",
	}
	if OS.has_feature("web"):
		var web: Variant=JSON.parse_string(str(JavaScriptBridge.eval("JSON.stringify({wasm_capacity_bytes:engine.rtenv.HEAPU8.buffer.byteLength,pack_file_bytes:GODOT_CONFIG.fileSizes[GODOT_CONFIG.mainPack||'elfienest.pck']})")))
		if web is Dictionary:report.merge(web)
		report["note"]="Zero static counters are unavailable in release builds. WASM capacity is allocated linear address space, not RSS. Render video includes texture/buffer counters: do not add them twice. Pack bytes are file size, not measured residency."
		JavaScriptBridge.eval("(()=>{let e=document.getElementById('estate-memory');if(!e){e=document.createElement('pre');e.id='estate-memory';e.style.cssText='position:fixed;bottom:8px;left:8px;max-width:95vw;max-height:45vh;overflow:auto;background:#111e;color:#fff;padding:10px;font:12px monospace;z-index:1000';document.body.appendChild(e)}e.textContent="+JSON.stringify(JSON.stringify(report,"  "))+"})()")
	print("ESTATE_MEMORY_RENDERED ",JSON.stringify(report))
	samples+=1;elapsed=0;frames=0;worst_frame_ms=0
	if samples>=5:set_process(false)
