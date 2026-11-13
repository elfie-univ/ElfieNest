extends Node
## Production-owned approved furniture motion. The Lab only submits a semantic target.
const RENDER_BATCHES := preload("res://nest/rendering/estate_instance_batches.gd")
var actor: ElfieActor
var stage := ""
var sleep: Node3D
var _cloth: MeshInstance3D
var _cloth_mesh: Mesh
var _command := ""

func run(body: ElfieActor, marker: Marker3D, anchor_id: String, variant: String, nest: ModularNest) -> Dictionary:
	actor = body
	_command = str(actor.get("furniture_cycle_command"))
	var error := ElfieActor.furniture_marker_error(marker)
	if not error.is_empty(): return _result("failed", error)
	if variant.begins_with("sleep-"):
		if str(marker.get_meta("kind")) != "bed": return _result("failed", "sleep_requires_bed")
		return await _sleep(marker, anchor_id, variant, nest)
	if variant != "seat" or str(marker.get_meta("kind")) != "chair": return _result("failed", "seat_requires_chair")
	var direct := preload("res://runtime/actor/direct_seat_cycle.gd").new()
	add_child(direct)
	return await direct.run(actor,marker,nest)

func _stage(value: String) -> void:
	stage = value
	actor.set_meta("furniture_cycle_stage", value)
	print("FURNITURE_CYCLE ", JSON.stringify({"actor_id":actor.elfie_id,"command_id":_command,"stage":value}))

func _result(status: String, reason: String = "") -> Dictionary:
	return {"status":status, "reason":reason}

func _failure(reason: String) -> Dictionary:
	return _result("cancelled" if bool(actor.get("cycle_cancelled")) else "failed", reason)

func _available() -> bool:
	return bool(actor.call("cycle_available"))

func _sleep(marker: Marker3D, anchor_id: String, variant: String, nest: ModularNest) -> Dictionary:
	# Shared GLB instances repeat node names across beds and rooms. The marker
	# owns the exact instance; a whole-estate name search selects the first bed.
	if not marker.has_meta("furniture_source"): return _result("failed", "bed_source_unavailable")
	var source := marker.get_meta("furniture_source") as MeshInstance3D
	if not is_instance_valid(source) or not nest.get_node("Generated/CompleteEstate").is_ancestor_of(source):
		return _result("failed", "bed_source_unavailable")
	var e := source.get_meta("extras", {}) as Dictionary
	var bedding: Array[MeshInstance3D] = []
	for mesh: MeshInstance3D in nest.get_node("Generated/CompleteEstate").find_children("*","MeshInstance3D",true,false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if extras.get("module") != e.get("module") or extras.get("resident") != e.get("resident"): continue
		if extras.get("piece") in ["bed_cover", "throw", "bed_cover_seam"]: bedding.append(mesh)
		if extras.get("piece") == "bed_cover": _cloth = mesh
	if _cloth == null: return _result("failed", "authored_duvet_unavailable")
	var error := actor.enter_furniture(marker,anchor_id)
	if not error.is_empty(): return _result("failed",error)
	# Release all authored layers before the first cloth replacement/attachment.
	# Exit restoration uses these same unbatched nodes throughout the sleep cycle.
	for mesh: MeshInstance3D in bedding: RENDER_BATCHES.restore_before_write(mesh)
	_cloth_mesh = _cloth.mesh
	_cloth.mesh = preload("res://nest/rendering/estate_surface.gd").duvet_rest(_cloth_mesh)
	preload("res://nest/furniture/shared/bedroom/estate_bedding_layers.gd").attach_bed(nest.get_node("Generated/CompleteEstate"),_cloth)
	sleep = preload("res://runtime/actor/sleep_cycle.gd").new()
	add_child(sleep)
	sleep.mode = "back" if variant == "sleep-back" else ("side-left" if variant == "sleep-left" else "side-right")
	sleep.bind(actor,_cloth,null)
	sleep.set_process(false)
	var seconds := 1.5
	if bool(nest.get_meta("lab_action_preview", false)):
		seconds = clampf(float(actor.get_meta("preview_sleep_start", 1.5)), 1.5, 15.5)
		actor.remove_meta("preview_sleep_start")
	var start_seconds := seconds
	var started_usec := Time.get_ticks_usec()
	var last := ""
	while seconds < 16.0:
		sleep.sample_bedding(seconds)
		if sleep.animation_stage != last:
			last = sleep.animation_stage
			_stage(last)
		await get_tree().process_frame
		if not _available(): return _failure("sleep_cancelled")
		seconds = start_seconds + float(Time.get_ticks_usec()-started_usec)/1000000.0 * Engine.time_scale
	sleep.sample_bedding(16.0)
	if not actor.leave_furniture(): return _result("failed","bed_exit_blocked")
	_stage("leave_and_lay_back")
	return _result("completed")

func _exit_tree() -> void:
	if is_instance_valid(_cloth) and _cloth_mesh != null:
		_cloth.mesh = _cloth_mesh
		if _cloth.has_meta("estate_bedding_layers"): _cloth.get_meta("estate_bedding_layers").restore()
	if is_instance_valid(actor): actor.remove_meta("furniture_cycle_stage")
