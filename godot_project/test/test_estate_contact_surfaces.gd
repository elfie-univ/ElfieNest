extends SceneTree
## Verify the imported display meshes, not only the source GLB measurements.

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	if not check_bedroom_contacts(estate) or not check_room_crown(estate): return
	var shelf := estate.find_child("Draft L2 curved bookcase continuous hidden diffuser",true,false) as MeshInstance3D
	if not require((shelf.global_transform*shelf.get_aabb()).end.y < 4.701,"Imported shelf lamp must expose the latest repaired lens below the timber"): return
	var desk := estate.find_child("Draft L3 writing desk concealed downward task lens",true,false) as MeshInstance3D
	var desk_box := desk.global_transform*desk.get_aabb()
	if not require(desk_box.size.y > 0.02 and desk_box.position.x > 7.77,"Imported writing lamp must be vertical on its backboard"): return
	var chair := estate.find_child("quiet_rear_reading_armchair",true,false) as MeshInstance3D
	var seat: PackedVector3Array = chair.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var legs: PackedVector3Array = chair.mesh.surface_get_arrays(1)[Mesh.ARRAY_VERTEX]
	var seat_bottom := INF
	var leg_top := -INF
	for point: Vector3 in seat: seat_bottom=minf(seat_bottom,point.y)
	for point: Vector3 in legs: leg_top=maxf(leg_top,point.y)
	if not require(leg_top>seat_bottom+0.002,"Imported reading-chair legs must actually reach the seat"): return
	var easel := estate.find_child("botanical_painting_easel",true,false) as MeshInstance3D
	# A tilted object's transformed AABB includes empty corners below its feet.
	# Measure the actual imported vertices in the room frame instead.
	var easel_bottom := INF
	for surface in range(easel.mesh.get_surface_count()):
		var points: PackedVector3Array = easel.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
		for point: Vector3 in points: easel_bottom=minf(easel_bottom,(easel.global_transform*point).y)
	if not require(easel_bottom > 3.12 and easel_bottom < 3.135,"Imported easel feet must meet the actual terrace rug instead of floating above it"): return
	var throw_mesh := estate.find_child("linen_throw_on_fitted_sofa",true,false) as MeshInstance3D
	if not require(throw_mesh.get_aabb().end.z < 0.60,"Imported M01 cloth must occupy the free gap between its cushions"): return
	var bedroom_lamps := 0
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		var e: Dictionary=mesh.get_meta("extras",{})
		if e.get("source_name","")=="Desk | amber globe":
			bedroom_lamps+=1
			if not require((mesh.global_transform*mesh.get_aabb()).size.y>0.18,"All imported desk globes must use the enlarged shared model"): return
	if not require(bedroom_lamps==32,"Retain all thirty-two bedroom desk lamps"): return
	print("PASS imported current contact repairs: supported reading chair, fitted writing lamp, exposed bookcase lamp, 32 enlarged desk lamps")
	estate.free()
	quit(0)

func check_bedroom_contacts(estate: Node3D) -> bool:
	var shells := {}
	var desks := {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		var module := str(extras.get("module", ""))
		if not module.begins_with("M") or not extras.has("resident"): continue
		var key := module + "/" + str(extras.resident)
		if extras.get("assembly") == "bed" and extras.get("piece") == "shell":
			if not require(not shells.has(key) and extras.get("source_name") == "Bed | complete independent pod shell", "Duplicate or misidentified bed shell: " + key): return false
			shells[key] = mesh
		if extras.get("piece") == "worktop":
			var expected_name := str(extras.resident) + " | longer curved desktop with compact rounded head joint"
			if not require(not desks.has(key) and extras.get("source_name") == expected_name, "Duplicate or misidentified worktop: " + key): return false
			desks[key] = mesh
	if not require(shells.size() == 32 and desks.size() == 32, "All 32 placed bed shells and worktops must remain present"): return false
	var minimum := INF
	var maximum := -INF
	var samples := 0
	var outside_legacy_tolerance := 0
	for key: String in shells:
		if not require(desks.has(key), "Bed has no matching resident worktop: " + key): return false
		var shell: MeshInstance3D = shells[key]
		var desk: MeshInstance3D = desks[key]
		var shell_faces := shell.mesh.get_faces()
		var desk_faces := desk.mesh.get_faces()
		var shell_pose := _saved_placement_pose(shell)
		var desk_pose := _saved_placement_pose(desk)
		if not require(not shell_pose.is_empty() and not desk_pose.is_empty(), "Bed/worktop lacks a canonical saved SCN placement: " + key): return false
		var expected_relative: Transform3D = (shell_pose.world as Transform3D).affine_inverse() * (desk_pose.world as Transform3D)
		var relative := shell.global_transform.affine_inverse() * desk.global_transform
		if not require(relative.is_equal_approx(expected_relative), "Bed/worktop relative contact frame differs from approved split SCN placement: " + key): return false
		for index: int in desk_faces.size(): desk_faces[index] = relative * desk_faces[index]
		var resident_samples := 0
		for height: float in [0.551, 0.575, 0.599]:
			for angle: float in [-101.0, -100.0, -90.0, -80.0, -70.0, -60.0, -56.0]:
				var direction := Vector2(cos(deg_to_rad(angle)), sin(deg_to_rad(angle)))
				var bed_radii := _section_radii(shell_faces, height, direction)
				var desk_radii := _section_radii(desk_faces, height, direction)
				if bed_radii.is_empty() or desk_radii.is_empty(): continue
				var gap: float = desk_radii.min() - bed_radii.max()
				if not require(is_finite(gap) and gap >= -0.007 and gap <= 0.001, "Bed/worktop contact outside [-0.007, 0.001] m: resident=%s height=%f angle=%f gap=%0.12f" % [key, height, angle, gap]): return false
				minimum = minf(minimum, gap)
				maximum = maxf(maximum, gap)
				outside_legacy_tolerance += int(gap < -0.007 or gap > 0.001)
				samples += 1
				resident_samples += 1
		if not require(resident_samples > 0, "No measurable bed/worktop adjacency for resident: " + key): return false
	print("BED_WORKTOP_CONTACT residents=", shells.size(), " samples=", samples, " minimum_gap=", minimum, " maximum_gap=", maximum, " outside_merged_tolerance=", outside_legacy_tolerance)
	return true

func _saved_placement_pose(mesh: MeshInstance3D) -> Dictionary:
	var scene_root: Node = mesh.get_parent()
	while scene_root != null and scene_root.scene_file_path.is_empty(): scene_root = scene_root.get_parent()
	if scene_root == null: return {}
	var scene := load(scene_root.scene_file_path) as PackedScene
	if scene == null: return {}
	var state := scene.get_state()
	var identity := str(mesh.get_meta("v044_path", ""))
	for index: int in state.get_node_count():
		var saved_identity := ""
		var pose := Transform3D.IDENTITY
		for property: int in state.get_node_property_count(index):
			var label := state.get_node_property_name(index, property)
			if label == &"metadata/v044_path": saved_identity = str(state.get_node_property_value(index, property))
			if label == &"transform": pose = state.get_node_property_value(index, property)
		if saved_identity != identity or identity.is_empty(): continue
		return {"world": (mesh.get_parent() as Node3D).global_transform * pose}
	return {}

func _section_radii(faces: PackedVector3Array, height: float, direction: Vector2) -> Array[float]:
	var result: Array[float] = []
	for start: int in range(0, faces.size(), 3):
		var section: Array[Vector2] = []
		for edge: int in 3:
			var a := faces[start + edge]
			var b := faces[start + (edge + 1) % 3]
			if absf(a.y - b.y) < 0.00000001 or height < minf(a.y, b.y) or height > maxf(a.y, b.y): continue
			var point := a.lerp(b, (height - a.y) / (b.y - a.y))
			section.append(Vector2(point.x, point.z))
		if section.size() != 2: continue
		var delta := section[1] - section[0]
		var denominator := direction.cross(delta)
		if absf(denominator) < 0.00000001: continue
		var radius := section[0].cross(delta) / denominator
		var along := section[0].cross(direction) / denominator
		if radius >= 0.0 and along >= 0.0 and along <= 1.0: result.append(radius)
	return result

func check_room_crown(estate: Node3D) -> bool:
	var rooms := {}
	var triangles := 0
	var degenerate := 0
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if extras.get("source_name") != "ROOM • sculpted continuous shell": continue
		rooms[str(extras.get("module", ""))] = true
		var faces := mesh.mesh.get_faces()
		var useful := 0
		for start: int in range(0, faces.size(), 3):
			var a := faces[start]
			var b := faces[start + 1]
			var c := faces[start + 2]
			if minf(a.y, minf(b.y, c.y)) < 3.099: continue
			if not require(a.is_finite() and b.is_finite() and c.is_finite(), "Crown has nonfinite geometry"): return false
			triangles += 1
			if (b-a).cross(c-a).length_squared() < 4e-20: degenerate += 1
			else: useful += 1
		if not require(useful > 0, "Room crown lost its visible nondegenerate surface"): return false
	print("ROOM_CROWN rooms=", rooms.size(), " triangles=", triangles, " approved_source_degenerate=", degenerate)
	return require(rooms.size() == 8, "All eight placed room crowns must remain present")
