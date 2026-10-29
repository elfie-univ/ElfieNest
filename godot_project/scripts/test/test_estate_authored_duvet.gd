extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var review = load("res://runtime/lab/estate_event_review.gd").new()
	root.add_child(review)
	review.set_process(false)
	var sleep = review.get_node("SleepPresentation")
	sleep.set_process(false)
	var authored: MeshInstance3D
	var room_floor: MeshInstance3D
	var throws := 0
	for mesh: MeshInstance3D in review.review_geometry.find_children("*", "MeshInstance3D", true, false):
		var e := mesh.get_meta("extras", {}) as Dictionary
		if e.get("module") == "M01" and str(e.get("source_name", "")).contains("continuous lower floor"):
			room_floor = mesh
		if e.get("module") == "M01" and e.get("resident") == "A":
			if e.get("piece") == "bed_cover": authored = mesh
			if e.get("piece") == "throw" and mesh.visible: throws += 1
	sleep.set_mode("back")
	for suffix: String in ["Hips", "Spine2", "Neck", "Head", "LeftFoot", "RightFoot"]:
		print("AUTHORED_DUVET_BONE ", suffix, " local=", authored.to_local(sleep._bone(suffix)))
	print("AUTHORED_DUVET mesh=", authored.mesh.get_aabb(), " vertices=", authored.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].size(), " visible_white_throw_parts=", throws)
	if not _check(sleep.blanket == authored, "Sleep must lift the original green bed_cover, not add another blanket above it"):
		return
	if not _check(sleep.has_method("sample_bedding"), "Original duvet has no lift/cover/lay-back animation"):
		return
	var rest_mesh = sleep.get("source_duvet_mesh")
	if not _check(rest_mesh.get_aabb().size.y < 0.05, "Resting duvet still has the rejected large padded quilting instead of small fabric wrinkles"):
		return
	var source_vertices: PackedVector3Array = rest_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for mode: String in ["back", "side-left", "side-right"]:
		sleep.set_mode(mode)
		sleep.sample_bedding(0.0)
		var room_center: Vector3 = room_floor.global_transform * room_floor.get_aabb().get_center()
		var bed_center: Vector3 = authored.global_transform * rest_mesh.get_aabb().get_center()
		var into_room: Vector3 = (room_center-bed_center)*Vector3(1,0,1)
		if not _check((sleep._bone("Hips")-bed_center).dot(into_room) > 0.0, "Actor approaches/stands on the wall side instead of the free room side of the real bed"):
			return
		var rest: PackedVector3Array = authored.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		if not _check(rest == source_vertices, "Empty-bed start does not retain the actual authored duvet"):
			return
		sleep.sample_bedding(1.8)
		if not _check(authored.mesh.get_aabb().end.y < rest_mesh.get_aabb().end.y+0.065, "Unoccupied folded duvet keeps an unsupported sleeping-body mound"):
			return
		var id := authored.get_instance_id()
		for seconds: float in [4.0, 4.8, 12.6, 13.4]:
			sleep.sample_bedding(seconds)
			var grip: Dictionary = sleep.get("grip_report")
			if not _check(not grip.is_empty() and float(grip.get("gap", 1.0)) < 0.025, "Covering/uncovering cloth is not held by the actual pulling hand"):
				return
		sleep.sample_bedding(7.0)
		var covered: PackedVector3Array = authored.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		if not _diagnose_edges(sleep,authored,mode): return
		for prefix: String in ["Left", "Right"]:
			var toe := authored.to_local(sleep._bone(prefix+"ToeBase"))
			if not _check(toe.x>rest_mesh.get_aabb().position.x+0.04 and toe.x<rest_mesh.get_aabb().end.x-0.04, "Relaxed toes leave the covered bed width in a side pose"):
				return
		if not _check(authored.get_instance_id() == id and covered.size() == source_vertices.size(), "Cover cycle replaced the original cloth identity/topology"):
			return
		if not _check(covered != source_vertices and authored.mesh.surface_get_material(0) == rest_mesh.surface_get_material(0), "Cover does not deform the original cloth with its original material"):
			return
		var coincident: Dictionary = {}
		for index in range(source_vertices.size()):
			var p := source_vertices[index]
			var key := Vector3i(roundi(p.x*100000),roundi(p.y*100000),roundi(p.z*100000))
			if coincident.has(key) and not _check(covered[index].distance_to(covered[int(coincident[key])]) < 0.0001, "Authored duvet UV seam split open during body contact correction"):
				return
			coincident[key] = index
		if not _check(authored.mesh.get_aabb().end.z >= rest_mesh.get_aabb().end.z - 0.01, "Cover ends at the actor feet instead of reaching the original bed foot"):
			return
		var middle := covered[covered.size() / 2]
		sleep.sample_bedding(7.01)
		var after: PackedVector3Array = authored.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		if not _check(after[after.size()/2].distance_to(middle) < 0.01, "Breathing/review animation jumps the duvet"):
			return
		sleep.sample_bedding(18.5)
		if not _check(authored.mesh == rest_mesh, "Leaving does not put that same original duvet back onto the bed"):
			return
	for mesh: MeshInstance3D in review.review_geometry.find_children("*", "MeshInstance3D", true, false):
		var e := mesh.get_meta("extras", {}) as Dictionary
		if e.get("module") == "M01" and e.get("resident") == "A" and e.get("piece") == "throw":
			if not _check(not mesh.visible, "Optional short white throw still overlaps the animated duvet"):
				return
	review.queue_free()
	await process_frame
	print("PASS same authored duvet/material/topology: flat -> lift -> back/left/right covered breathing -> lay back; optional white throw removed locally")
	quit(0)

func _check(value: bool, message: String) -> bool:
	if not value:
		push_error(message)
		quit(1)
	return value

func _diagnose_edges(sleep: Node3D, cloth: MeshInstance3D, mode: String) -> bool:
	var body: Node3D = sleep.get("_body")
	var skeleton: Skeleton3D = sleep.get("_hips")
	var points: PackedVector3Array = sleep.DUVET.skin_points(body,skeleton)
	var offset := 0
	var extrema: Dictionary = {}
	for mesh: MeshInstance3D in body.find_children("*","MeshInstance3D",true,false):
		if mesh.skin==null or mesh.mesh==null: continue
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var stride := bones.size()/vertices.size()
			for i in range(vertices.size()):
				var point := cloth.to_local(points[offset+i])
				if point.z<0.2 or point.z>0.9: continue
				var slot := 0
				for j in range(1,stride):
					if weights[i*stride+j]>weights[i*stride+slot]: slot=j
				var name := str(mesh.skin.get_bind_name(bones[i*stride+slot]))
				if not extrema.has(name): extrema[name]=[point.x,point.x,point.y]
				extrema[name]=[minf(extrema[name][0],point.x),maxf(extrema[name][1],point.x),maxf(extrema[name][2],point.y)]
			offset+=vertices.size()
	var tail: Array = extrema.get("mixamorig_Tail_Bone",[])
	print("SLEEP_TUCKED_TAIL ",mode," ",tail)
	return _check(not tail.is_empty() and tail[0]>=cloth.mesh.get_aabb().position.x and tail[1]<=cloth.mesh.get_aabb().end.x,"Side sleeping tail extends outside the original duvet")
