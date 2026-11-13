extends RefCounted
## Complete static seating, bound to the actual estate furniture instances.

const LABELS := {
	"living_reference_chair_left":"左侧单人沙发", "living_reference_chair_right":"右侧单人沙发",
	"games_central_chair_":"中央游戏区·座椅", "games_left_chess_chair_":"左侧棋桌·座椅",
	"games_right_console_chair_":"右侧电玩区·座椅", "quiet_central_reading_chair_":"中央阅读区·座椅",
	"quiet_right_journaling_chair_":"右侧书写区·座椅", "quiet_rear_reading_armchair":"后侧阅读区·单人沙发",
	"quiet_left_sofa_seat_":"左侧阅读沙发·坐位",
	"games_front_pouf_":"前侧游戏区·坐墩", "quiet_rear_footstool":"后侧阅读区·脚凳",
	"quiet_front_daybed_mattress":"前侧日间躺榻",
	"wall_fitted_gaming_sofa":"电玩长沙发", "blue_gaming_pouf":"蓝色坐墩", "cream_gaming_pouf":"米色坐墩",
	"cream_reading_armchair":"米色阅读单人沙发", "sage_reading_armchair":"绿色阅读单人沙发",
	"reading_ottoman":"阅读脚凳", "lilac_game_armchair_":"桌游单人沙发",
	"wall_fitted_music_loveseat":"音乐双人沙发", "sage_listening_armchair":"绿色聆听单人沙发",
	"craft_stool":"手作坐墩", "apricot_craft_armchair":"杏色手作单人沙发",
	"right_wall_fitted_tea_sofa":"右侧茶叙沙发", "woven_floor_cushion_one":"编织坐垫 1",
	"woven_floor_cushion_two":"编织坐垫 2", "blue_collectors_armchair":"蓝色收藏单人沙发",
	"blue_matching_ottoman":"蓝色脚凳",
}

func append(geometry: Node3D, seats: Array[Dictionary]) -> void:
	var meshes := geometry.find_children("*", "MeshInstance3D", true, false)
	for mesh: MeshInstance3D in meshes:
		if mesh.mesh == null: continue
		var e := mesh.get_meta("extras", {}) as Dictionary
		var module := str(e.get("module", ""))
		var source := str(e.get("source_name", mesh.name))
		var object := str(e.get("central_furnishing", source))
		var level := int(e.get("floor", 0))
		var kind := str(e.get("kind", ""))
		var zone := ""
		var name := object
		var floor_y := 0.0
		var front := mesh.global_basis.z.normalized()
		var point := mesh.get_aabb().get_center()
		if module == "central":
			var barrel := object.begins_with("living_reference_chair_") and "inset plump seat" in source
			var reading_sofa := source.begins_with("quiet_left_sofa_seat_")
			var daybed := source == "quiet_front_daybed_mattress"
			if not barrel and not reading_sofa and not daybed and kind not in ["chair", "stool"]: continue
			zone = "central-%02d" % level
			floor_y = 0.3 if level == 1 else (4.3 if level == 2 else 7.1)
			if barrel:
				for other: MeshInstance3D in meshes:
					var other_e := other.get_meta("extras", {}) as Dictionary
					if other_e.get("central_furnishing") == object and "lumbar pillow" in str(other_e.get("source_name", other.name)):
						front = mesh.to_global(point) - (other.global_transform * other.get_aabb()).get_center()
			elif reading_sofa or daybed:
				front = Vector3.ZERO - mesh.to_global(point)
			else:
				point.z += mesh.get_aabb().size.z * 0.15
		elif module.begins_with("M") and level == 2:
			if kind not in ["chair", "sofa", "ottoman", "stool", "floor_cushion"] or "throw" in object: continue
			# These two contacts already retain their approved mount calibration.
			if object in ["M01_sofa_following_actual_wall", "M07_left_wall_fitted_tea_sofa"]: continue
			zone = "terrace-%02d" % int(module.trim_prefix("M"))
			name = object.trim_prefix(module + "_")
			var floor_mesh: MeshInstance3D
			for other: MeshInstance3D in meshes:
				var other_e := other.get_meta("extras", {}) as Dictionary
				if other_e.get("module") == module and "inset terrace walking finish" in str(other_e.get("source_name", other.name)):
					floor_mesh = other; break
			if floor_mesh == null: push_error("Seat floor missing: " + object); continue
			floor_y = (floor_mesh.global_transform * floor_mesh.get_aabb()).end.y
			if kind == "sofa":
				var radial := Vector3(point.x, 0, point.z).normalized()
				point.x = radial.x * 2.05; point.z = radial.z * 2.05
				front = mesh.global_basis * -radial
				if name == "right_wall_fitted_tea_sofa":
					# The L-shaped seat leaves its bounds centre empty; sample its east run.
					point.x = 2.2; point.z = 0.4
					front = mesh.global_basis * Vector3.LEFT
			elif kind == "chair":
				point.z += mesh.get_aabb().size.z * 0.15
		else: continue
		front.y = 0
		front = front.normalized()
		var contact := _surface(mesh, mesh.to_global(point), floor_y)
		if not contact.is_finite(): push_error("Seat surface missing: " + object); continue
		var id := zone + "/" + name.replace("_", "-")
		seats.append({"id":id, "anchor_id":id, "label":_label(name), "source":mesh,
			"contact":Transform3D(Basis(Vector3.UP, atan2(front.x, front.z)), contact), "floor_y":floor_y})

func _label(name: String) -> String:
	if LABELS.has(name): return str(LABELS[name])
	for prefix: String in LABELS:
		if prefix.ends_with("_") and name.begins_with(prefix):
			return "%s %d" % [LABELS[prefix], int(name.trim_prefix(prefix)) + 1]
	return name

func _surface(mesh: MeshInstance3D, center: Vector3, floor_y: float) -> Vector3:
	# Intersect real triangles, not the top of a chair/backrest's bounding box.
	var highest := -INF
	var faces := mesh.mesh.get_faces()
	var top := Vector3(center.x, floor_y + 0.84, center.z)
	var bottom := Vector3(center.x, floor_y + 0.04, center.z)
	for index in range(0, faces.size(), 3):
		var hit: Variant = Geometry3D.segment_intersects_triangle(top, bottom,
			mesh.to_global(faces[index]), mesh.to_global(faces[index + 1]), mesh.to_global(faces[index + 2]))
		if hit != null: highest = maxf(highest, (hit as Vector3).y)
	return Vector3(center.x, highest, center.z) if is_finite(highest) else Vector3.INF
