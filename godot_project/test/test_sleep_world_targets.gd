extends SceneTree
## Exercise real split-world beds, including mirrored beds and rotated rooms.
const NEST := preload("res://nest/nest.tscn")
const CYCLE := preload("res://runtime/actor/furniture_cycle.gd")
const SLEEP := preload("res://runtime/actor/sleep_cycle.gd")
const DUVET := preload("res://runtime/actor/authored_duvet.gd")
var failures := 0

class ContactProbe extends ElfieActor:
	func enter_furniture(_marker: Marker3D, _anchor_id: String) -> String: return "contact_probe"

func _initialize() -> void:
	create_timer(180.0).timeout.connect(func() -> void: push_error("Sleep world regression timed out"); quit(1))
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok: failures += 1; push_error(message)

func run() -> void:
	var nest := NEST.instantiate() as ModularNest; root.add_child(nest)
	await process_frame
	var probe := ContactProbe.new()
	var covers := {}
	for room in range(1,9):
		for bed in range(1,5):
			var id := "dorm-%02d/bed-%02d" % [room,bed]
			var marker := nest.resolve_anchor(id)
			if marker == null: check(false,"Missing real bed "+id); continue
			var runner := CYCLE.new(); runner.actor = probe
			var result: Dictionary = await runner._sleep(marker,id,"sleep-left",nest)
			check(result.reason == "contact_probe", "Could not resolve bed "+id)
			if runner._cloth != null:
				var e: Dictionary = runner._cloth.get_meta("extras",{})
				check(e.get("module") == "M%02d"%room and e.get("resident") == "ABCD"[bed-1], "Wrong real bed duvet "+id)
				covers[id] = runner._cloth
			runner.free()
	probe.free()
	if failures: nest.free(); quit(1); return
	for item: Array in [["saevi","dorm-01/bed-01"],["saevi","dorm-01/bed-04"],["saevi","dorm-02/bed-02"],["saevi","dorm-08/bed-03"],["tovren","dorm-01/bed-04"]]:
		var marker := nest.resolve_anchor(item[1])
		var cloth := covers[item[1]] as MeshInstance3D
		var original := cloth.mesh
		for mode: String in ["back","side-left","side-right"]:
			var actor := (load("res://characters/%s/%s.tscn"%[item[0],item[0]]) as PackedScene).instantiate() as ElfieActor
			root.add_child(actor); actor.configure("sleep-test",marker.global_position)
			actor.set_physics_process(false)
			check(actor.enter_furniture(marker,item[1]).is_empty(),"Could not enter "+str(item))
			var cycle := SLEEP.new(); cycle.mode = mode; root.add_child(cycle)
			var started := Time.get_ticks_usec(); cycle.bind(actor,cloth,null); cycle.set_process(false)
			var preparation_us := Time.get_ticks_usec()-started
			var toward_room := marker.global_position-cloth.to_global(cycle.source_duvet_mesh.get_aabb().get_center())
			toward_room.y = 0.0
			check(cycle._walk_direction.dot(toward_room)>0.0,"Sleep enters from the wall side: "+str(item)+mode)
			cycle.sample_bedding(7.0)
			var hips: Vector3 = cloth.to_local(cycle._bone("Hips"))
			var head: Vector3 = cloth.to_local(cycle._bone("Head"))
			check(head.z < hips.z-0.15,"Head points away from actual pillow: "+str(item)+mode)
			check(absf(hips.x-cloth.mesh.get_aabb().get_center().x)<0.15,"Sleep drifts sideways from its bed: "+str(item)+mode)
			var started_sample := Time.get_ticks_usec()
			for seconds: float in [2.0,2.8,4.0,4.6,7.3,13.0,14.5,15.5]: cycle.sample_bedding(seconds)
			print("SLEEP_POSE ",JSON.stringify({"species":item[0],"bed":item[1],"mode":mode,"head":head,"hips":hips,"prepare_us":preparation_us,"sample_us":(Time.get_ticks_usec()-started_sample)/8.0}))
			cycle.free(); actor.free(); cloth.mesh = original
			if cloth.has_meta("estate_bedding_layers"): cloth.get_meta("estate_bedding_layers").sample()
	nest.free()
	print("SLEEP_WORLD_TARGETS beds=32 poses=15 failures=",failures)
	quit(1 if failures else 0)
