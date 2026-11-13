extends SceneTree
## Real imported assets, sleep controller, wake and command cancellation/reuse.
const NEST := preload("res://nest/nest.tscn")
const SLEEP := preload("res://runtime/actor/sleep_cycle.gd")
const SHAPES := ["Sleep_EyesQuarter", "Sleep_EyesHalf", "Sleep_EyesThreeQuarter", "Sleep_EyesClosed"]

class CycleCall extends RefCounted:
	var done := false
	var result: Dictionary = {}
	func start(actor: ElfieActor, marker: Marker3D, nest: ModularNest) -> void:
		result = await actor.play_furniture_cycle(marker,"dorm-01/bed-01","eyes-cancel","sleep-back",nest)
		done = true

func _initialize() -> void:
	create_timer(90.0).timeout.connect(func() -> void: push_error("Sleep eyelid integration timed out"); quit(1))
	call_deferred("run")

func check(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func expect(actor: ElfieActor, expected: Array, label: String) -> bool:
	var found := false
	for mesh: MeshInstance3D in actor.find_children("*","MeshInstance3D",true,false):
		if mesh.mesh == null or mesh.find_blend_shape_by_name(SHAPES[0]) < 0: continue
		found = true
		for index in range(4):
			var key := mesh.find_blend_shape_by_name(SHAPES[index])
			if not check(key >= 0,"Incomplete formal eyelid asset: " + actor.species_id): return false
			if not check(is_equal_approx(mesh.get_blend_shape_value(key),float(expected[index])),label + " " + actor.species_id + " " + SHAPES[index]): return false
	return check(found,"Formal asset has no eyelid shapes: " + actor.species_id)

func run() -> void:
	var nest := NEST.instantiate() as ModularNest; root.add_child(nest)
	await process_frame
	var marker := nest.resolve_anchor("dorm-01/bed-01")
	var cloth: MeshInstance3D
	for mesh: MeshInstance3D in nest.get_node("Generated/CompleteEstate").find_children("*","MeshInstance3D",true,false):
		var extras: Dictionary = mesh.get_meta("extras",{})
		if extras.get("module") == "M01" and extras.get("resident") == "A" and extras.get("piece") == "bed_cover": cloth = mesh
	if not check(cloth != null,"Missing authored test-bed duvet"): return
	var original := cloth.mesh
	for species: String in ["saevi","tovren"]:
		var actor := (load("res://characters/%s/%s.tscn" % [species,species]) as PackedScene).instantiate() as ElfieActor
		root.add_child(actor); actor.configure("eyes-" + species,marker.global_position); actor.set_physics_process(false)
		if not expect(actor,[0,0,0,0],"initial"): return
		for mode: String in ["back","side-left","side-right"]:
			actor.global_position = marker.global_position
			if not check(actor.enter_furniture(marker,"dorm-01/bed-01").is_empty(),"Could not enter bed"): return
			var cycle := SLEEP.new(); cycle.mode = mode; root.add_child(cycle); cycle.bind(actor,cloth,null)
			for item: Array in [[5.0,[0,0,0,0]],[5.25,[0,1,0,0]],[5.5,[0,0,0,1]],[7.0,[0,0,0,1]],[12.2,[0,1,0,0]],[12.4,[0,0,0,0]],[16.0,[0,0,0,0]]]:
				cycle.sample_bedding(float(item[0]))
				if not expect(actor,item[1],mode + " t=" + str(item[0])): return
			cycle.sample_bedding(7.0)
			cycle.free()
			if not expect(actor,[0,0,0,0],"mid-sleep controller exit"): return
			if not check(actor.leave_furniture(),"Sleep exit blocked"): return
			actor.get("_animation_runtime").advance(1.0)
			if not expect(actor,[0,0,0,0],"standing after sleep"): return
			cloth.mesh = original
			if cloth.has_meta("estate_bedding_layers"): cloth.get_meta("estate_bedding_layers").sample()
		# Exercise the actual asynchronous command cancellation twice on the same actor.
		nest.set_meta("lab_action_preview",true)
		for repetition in range(2):
			actor.global_position = marker.global_position
			actor.set_meta("preview_sleep_start",7.0)
			var call := CycleCall.new(); call.start.call_deferred(actor,marker,nest)
			for frame in range(60):
				if actor.get_meta("furniture_cycle_stage","") == "covered_breathing" or call.done: break
				await process_frame
			if not check(not call.done and actor.get_meta("furniture_cycle_stage","") == "covered_breathing","Sleep command did not reach breathing"): return
			if not expect(actor,[0,0,0,1],"before command cancellation"): return
			actor.cancel_furniture_cycle("eyelid_regression")
			for frame in range(60):
				if call.done: break
				await process_frame
			if not check(call.done and call.result.get("status") == "cancelled","Cancellation did not terminate sleep"): return
			await process_frame
			await process_frame
			if not expect(actor,[0,0,0,0],"cancelled command cleanup"): return
			if not check(actor.leave_furniture(),"Cancelled actor cannot leave bed"): return
			actor.get("_animation_runtime").advance(1.0)
		actor.free()
	nest.free()
	print("PASS real sleep eyelids: both species, three poses, wake, cancellation and actor reuse")
	quit(0)
