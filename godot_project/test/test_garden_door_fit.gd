extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var estate := (load("res://nest/assembly/estate.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(estate)
	var frame := estate.find_child("Central L1 rounded garden entrance", true, false) as MeshInstance3D
	var glass := estate.find_child("Central L1 curved front glass", true, false) as MeshInstance3D
	var door = load("res://nest/estate/estate_garden_door.gd").new()
	door.build(estate, frame, glass, false)
	var inner_depths: Array[float] = []
	for vertex: Vector3 in frame.mesh.get_faces():
		var point := frame.global_transform * vertex
		if absf(absf(point.x - door.opening_bounds.get_center().x) - (door.opening_bounds.size.x * 0.5 + 0.01)) < 0.002 and point.y > door.opening_bounds.position.y + 0.3 and point.y < door.opening_bounds.get_center().y + 0.4:
			inner_depths.append(point.z)
	if inner_depths.is_empty():
		push_error("Could not find the frame's inner vertical face")
		quit(1)
		return
	var frame_depth := 0.0
	for depth in inner_depths: frame_depth += depth / inner_depths.size()
	if absf(door.opening_bounds.get_center().z - frame_depth) > 0.003:
		push_error("Door and frame are separated in depth by %f m" % absf(door.opening_bounds.get_center().z - frame_depth))
		quit(1)
		return
	var faces := frame.mesh.get_faces()
	for step in range(97):
		var x := lerpf(door.opening_bounds.position.x, door.opening_bounds.end.x, float(step) / 96.0)
		var expected: float = door.opening_bounds.end.y
		for index in range(0, faces.size(), 3):
			for edge in range(3):
				var a: Vector3 = frame.global_transform * faces[index + edge]
				var b: Vector3 = frame.global_transform * faces[index + (edge + 1) % 3]
				if absf(a.x-b.x) < 0.000001 or x < minf(a.x,b.x) or x > maxf(a.x,b.x): continue
				var y := lerpf(a.y,b.y,(x-a.x)/(b.x-a.x))
				if y > door.opening_bounds.end.y - 0.4: expected = minf(expected, y - 0.01)
		if absf(door._profile_top(x) - expected) > 0.002:
			push_error("Door upper edge does not match frame at x=%f: actual=%f expected=%f" % [x, door._profile_top(x), expected])
			quit(1)
			return
	print("PASS: both door upper edges follow the real frame")
	estate.queue_free()
	quit(0)
