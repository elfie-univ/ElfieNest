extends SceneTree
## A resident must keep correct bed-local poses after reusing its rig elsewhere.
const NEST := preload("res://nest/nest.tscn")
const SLEEP := preload("res://runtime/actor/sleep_cycle.gd")
func _initialize() -> void:
	create_timer(90.0).timeout.connect(func() -> void: push_error("Reused sleep rig timed out"); quit(1))
	call_deferred("run")

func check(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok

func run() -> void:
	var nest := NEST.instantiate() as ModularNest; root.add_child(nest)
	await process_frame
	var estate := nest.get_node("Generated/CompleteEstate")
	var covers := {}
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		var e: Dictionary = mesh.get_meta("extras",{})
		if e.get("piece") == "bed_cover": covers[str(e.get("module"))+str(e.get("resident"))] = mesh
	for species: String in ["saevi","tovren"]:
		var actor := (load("res://characters/%s/%s.tscn"%[species,species]) as PackedScene).instantiate() as ElfieActor
		root.add_child(actor); actor.configure("reuse-test",Vector3.ZERO); actor.set_physics_process(false)
		for item: Array in [["dorm-01/bed-01","M01A","back"],["dorm-01/bed-04","M01D","side-left"],["dorm-08/bed-03","M08C","side-right"],["dorm-02/bed-02","M02B","side-left"],["dorm-01/bed-01","M01A","back"]]:
			var marker := nest.resolve_anchor(item[0]); var cloth := covers[item[1]] as MeshInstance3D
			var original := cloth.mesh
			actor.global_position = marker.global_position; actor.velocity = Vector3.ZERO
			if not check(actor.enter_furniture(marker,item[0]).is_empty(),"Reused actor could not enter "+str(item)): return
			var cycle := SLEEP.new(); cycle.mode = item[2]; root.add_child(cycle); cycle.bind(actor,cloth,null)
			cycle.sample_bedding(7.0)
			var tail_direction: Vector3 = (cycle._bone("Tail_06")-cycle._bone("Tail_Bone")).normalized()
			if not check(tail_direction.dot(-cycle._axis)>0.65 and absf(tail_direction.y)<0.65,"Sleep left the six-joint tail upright: "+species+str(item)+" direction="+str(tail_direction)): return
			var head: Vector3 = cloth.to_local(cycle._bone("Head")); var hips: Vector3 = cloth.to_local(cycle._bone("Hips"))
			if not check(head.z < hips.z-0.15 and absf(hips.x-cycle.source_duvet_mesh.get_aabb().get_center().x)<0.15,"Reused actor drifted from bed-local pose: "+species+str(item)): return
			cycle.sample_bedding(16.0)
			if not check(actor.leave_furniture(),"Reused actor exit blocked: "+species+str(item)): return
			actor.get("_animation_runtime").advance(1.0)
			cycle.free(); cloth.mesh = original
			if cloth.has_meta("estate_bedding_layers"): cloth.get_meta("estate_bedding_layers").sample()
			print("SLEEP_REUSED_ACTOR ",species," ",item[0]," ",item[2])
		actor.free()
	nest.free()
	print("PASS same actor changes beds, rooms, left/right poses and returns upright")
	quit(0)
