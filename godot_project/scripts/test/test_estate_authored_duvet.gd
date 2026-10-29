extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	if not _check_static_bedding(): return
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
	var static_vertices: PackedVector3Array = _static_rest.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	if not _check(rest_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == static_vertices, "Sleep binding changes the ordinary static duvet or flattens it twice"):
		return
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
		var white: MeshInstance3D = _white_throw(authored)
		if not _check(white != null and white.visible, "Missing retained original white throw"): return
		var white_rest := white.mesh
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
			if not _check_white_follow(authored, white): return
		sleep.sample_bedding(7.0)
		if not _check(white.mesh != white_rest, "White throw stays frozen while the green duvet covers the body"): return
		if not _check_white_follow(authored, white): return
		var white_covered: PackedVector3Array = white.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
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
		if not _check(white.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] != white_covered, "White throw stops following after the first dynamic cloth frame"): return
		var after: PackedVector3Array = authored.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		if not _check(after[after.size()/2].distance_to(middle) < 0.01, "Breathing/review animation jumps the duvet"):
			return
		for seconds: float in [16.0, 18.5, 19.99, 20.0]:
			sleep.sample_bedding(seconds)
			if not _check(authored.mesh == rest_mesh and authored.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == static_vertices, "Leaving/loop restart does not restore the same ordinary static small-wrinkle duvet"):
				return
			if not _check(white.mesh == white_rest, "White throw does not return to the exact same small-wrinkle rest mesh"): return
	for mesh: MeshInstance3D in review.review_geometry.find_children("*", "MeshInstance3D", true, false):
		var e := mesh.get_meta("extras", {}) as Dictionary
		if e.get("module") == "M01" and e.get("resident") == "A" and e.get("piece") == "throw":
			if not _check(mesh.visible, "The retained white throw or its bound edge/fringe disappeared"):
				return
	review.queue_free()
	await process_frame
	print("PASS same authored duvet/material/topology: flat -> lift -> back/left/right covered breathing -> lay back; white throw retained and follows the duvet")
	quit(0)

var _static_rest: Mesh

func _check_static_bedding() -> bool:
	var estate: Node3D = load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(estate)
	var sources: Dictionary = {}
	var originals: Dictionary = {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if (mesh.get_meta("extras", {}) as Dictionary).get("piece") != "bed_cover": continue
		sources[mesh] = mesh.mesh
		originals[mesh] = mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	preload("res://rooms/estate/estate_daylight.gd").apply(estate)
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("piece") == "throw" and "folded linen" in str(e.get("source_name", "")):
			if not _check(mesh.mesh.get_aabb().size.y < 0.05, "White throw still has large rigid folds instead of lying against the fine-wrinkle duvet"): return false
	if not _check(not sources.is_empty(), "Static bedding fixture contains no authored duvets"): return false
	for mesh: MeshInstance3D in sources:
		if not _check(mesh.mesh.get_aabb().size.y < 0.05, "Ordinary static bed still uses large quilting before any sleep controller binds"): return false
		var source: Mesh = sources[mesh]
		var raw: PackedVector3Array = originals[mesh]
		var prepared: PackedVector3Array = mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		for i in range(raw.size()):
			if raw[i].y < source.get_aabb().position.y+0.015:
				if not _check(prepared[i].y < source.get_aabb().position.y+0.022, "Duvet rim still floats above the fitted pad as a vertical ledge"): return false
		if not _check(source.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == originals[mesh], "Static bedding repair mutated the shared imported source mesh"): return false
		if not _check(mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV] == source.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV] and mesh.mesh.surface_get_material(0) == source.surface_get_material(0), "Static bedding repair changed the original UVs or material"): return false
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("module") == "M01" and e.get("resident") == "A": _static_rest = mesh.mesh
	if not _check(_static_rest != null, "Missing representative M01/A static duvet"): return false
	print("STATIC_DUVETS small wrinkles=", sources.size())
	estate.free()
	return true

func _white_throw(cloth: MeshInstance3D) -> MeshInstance3D:
	for layer: Dictionary in cloth.get_meta("estate_bedding_layers").layers:
		var mesh: MeshInstance3D = layer["mesh"]
		if "folded linen" in str((mesh.get_meta("extras", {}) as Dictionary).get("source_name", "")): return mesh
	return null

func _check_white_follow(cloth: MeshInstance3D, white: MeshInstance3D) -> bool:
	var arrays := cloth.mesh.surface_get_arrays(0)
	var green: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var points: PackedVector3Array = white.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var frame := cloth.global_transform.affine_inverse()*white.global_transform
	var checked := 0
	for i in range(0, points.size(), 900):
		var point := frame*points[i]
		var top := -INF
		for j in range(0, indices.size(), 3):
			var hit: Variant = Geometry3D.ray_intersects_triangle(Vector3(point.x,10,point.z), Vector3.DOWN, green[indices[j]], green[indices[j+1]], green[indices[j+2]])
			if hit is Vector3: top = maxf(top, (hit as Vector3).y)
		if top == -INF: continue
		checked += 1
		if not _check(point.y-top >= 0.003 and point.y-top < 0.025, "White throw intersects the green duvet or floats above it during cover/uncover: gap="+str(point.y-top)): return false
	return _check(checked >= 5, "Too few real white/green cloth contacts were checked")

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
