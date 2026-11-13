extends RefCounted
## Seat contacts restored on the approved estate geometry. No copied world or animation.
var geometry: Node3D
var seats: Array[Dictionary] = []

func bind(source: Node3D) -> Array[Dictionary]:
	geometry = source
	bind_seats()
	return seats

func bind_seats() -> bool:
	seats.clear()
	var cushion := _find("central", "Upholstery V3 fitted full-depth seat cushion 1")
	if cushion == null: return false
	var bounds := cushion.global_transform * cushion.get_aabb()
	seats.append({"source": cushion, "id": "F08", "label": "客厅长沙发·中间", "contact": Transform3D(Basis.IDENTITY, Vector3(bounds.get_center().x, bounds.end.y, bounds.end.z - 0.08)), "floor_y": 0.3})
	# The side cushions are independent authored surfaces of the same sofa.
	for side in [0, 2]:
		var side_mesh := _find("central", "Upholstery V3 fitted full-depth seat cushion %d" % side)
		if side_mesh == null: continue
		var side_bounds := side_mesh.global_transform * side_mesh.get_aabb()
		var forward := Vector3(0.65 if side == 0 else -0.65, 0, 0.76).normalized()
		var reach := 0.0
		for vertex: Vector3 in side_mesh.mesh.get_faces():
			reach = maxf(reach, forward.dot(side_mesh.to_global(vertex) - side_bounds.get_center()))
		var position := side_bounds.get_center() + forward * (reach - 0.08)
		position.y = side_bounds.end.y
		seats.append({"source": side_mesh, "id": "F08-left" if side == 0 else "F08-right", "label": "客厅长沙发·左侧" if side == 0 else "客厅长沙发·右侧", "contact": Transform3D(Basis(Vector3.UP, atan2(forward.x, forward.z)), position), "floor_y": 0.3})
	# Per-seat contact annotations, measured on original seat surfaces. These
	# are furniture inputs, not copied animation files or relocated furniture.
	if not _terrace_seat("F10", "观影长沙发", "M01", "sofa_following_actual_wall", Vector3(-1.1, 3.705, 1.70), Vector3(0, 0, -1)): return false
	if not _terrace_seat("F13", "左侧茶叙沙发", "M07", "left_wall_fitted_tea_sofa", Vector3(-1.72, 3.705, 1.39), Vector3(0.403, 0, -0.915)): return false
	preload("res://nest/spatial/estate_seat_catalog.gd").new().append(geometry, seats)
	for seat: Dictionary in seats:
		print("TOUR_SEAT ", seat["id"], " contact=", seat["contact"], " floor=", seat["floor_y"])
	return true


func _find(module: String, name: String) -> MeshInstance3D:
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var e := mesh.get_meta("extras", {}) as Dictionary
		if e.get("module") == module and String(e.get("source_name", mesh.name)) == name: return mesh
	return null


func _terrace_seat(id: String, label: String, module: String, name: String, local: Vector3, front: Vector3) -> bool:
	var mesh := _find(module, name)
	if mesh == null: return false
	var contact := mesh.to_global(local)
	var direction := (mesh.global_basis * front).normalized()
	direction.y = 0
	var basis := Basis(Vector3.UP, atan2(direction.x, direction.z))
	var floor := _find(module, "ROOM • inset terrace walking finish")
	if floor == null: return false
	var floor_y := (floor.global_transform * floor.get_aabb()).end.y
	seats.append({"source": mesh, "id": id, "label": label, "contact": Transform3D(basis, contact), "floor_y": floor_y})
	return true
