extends Node3D
## Existing review entry displays the actual composed estate and its shared lights.
var camera_owner: Node3D
var _control: RefCounted
var _water: Node3D
var _night := false
var _quiet := false
var _people: Array[Dictionary] = []

func _ready() -> void:
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	add_child(estate)
	var reference := load("res://rooms/nest.tscn").instantiate() as Node3D
	var world := reference.get_node("WorldEnvironment") as WorldEnvironment
	reference.remove_child(world)
	reference.free()
	add_child(world)
	_control = preload("res://rooms/estate/estate_lighting_sample.gd").new()
	_control.bind_m01(self)
	_water = preload("res://rooms/estate/estate_water_display.gd").new()
	add_child(_water)
	_water.bind(estate,world.environment,false)
	if OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('people')||''")) == "1":
		_people = add_review_people(self, estate)
	var lake := estate.find_child("COMPLETE Inset natural lake",true,false) as MeshInstance3D
	var lake_center := (lake.global_transform*lake.get_aabb()).get_center()
	var trail := estate.find_child("FOREST TRAIL smooth gravel main loop and return spur",true,false)
	var path: Array = (trail.get_meta("extras") as Dictionary).forest_trail_paths[0]
	var start: Array = path[mini(40,path.size()-2)]
	var ahead: Array = path[mini(65,path.size()-1)]
	var eye := Vector3(start[0],start[1]+2.0,start[2])
	var target := Vector3(ahead[0],ahead[1]+0.3,ahead[2])
	var views: Array[Dictionary] = []
	var specifications: Array = [
		["Overview",Vector3(49,46,61),Vector3(0,1,4)],
		["Central",Vector3(21,17,28),Vector3(0,5.8,0)],
		["Middle",Vector3(0,5.8,5.5),Vector3(0,5.3,0)],
		["Upper",Vector3(0,8.6,5.5),Vector3(0,8.1,0)],
		["Plaza",Vector3(0,15,43),Vector3(0,0.5,23)],
		["Ring",Vector3(-14,2.2,-14),Vector3(-7,0.6,-18)],
		["Forest",eye,target],
		["Lake",lake_center+Vector3(20,24,28),lake_center],
		["Seats",Vector3(42,6,12),Vector3(31,0.5,3)]
	]
	var living := _living_view(estate)
	if not living.is_empty(): specifications.insert(2, living)
	for person: Dictionary in _people:
		var actor := person.actor as ElfieActor
		var person_target := actor.global_position + Vector3.UP * 0.45
		var person_eye := actor.global_position + actor.global_basis.z * 2.3 + actor.global_basis.x * 0.95 + Vector3.UP * 1.1
		specifications.append([person.label, person_eye, person_target])
	for spec: Array in specifications:
		for mode: String in ["day","night","quiet"]:
			var label := {"day":"Day 06–18","night":"Evening 18–24","quiet":"Quiet 00–06"}
			views.append({"id":"lighting-v4-"+str(spec[0]).to_lower()+"-"+mode,"focus":str(spec[0])+" / "+str(label[mode]),"camera":spec[1],"target":spec[2],"fov":58.0})
	camera_owner.configure_estate_path_lighting_review(views)
	var selected := "lighting-v4-overview-night"
	if OS.has_feature("web"):
		var requested := str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('view')||''"))
		if requested.begins_with("lighting-v4-"): selected = requested
	camera_owner.select_observer_camera_by_id(selected)
	set_phase(not selected.ends_with("day"),selected.ends_with("quiet"))

func set_phase(night: bool, quiet: bool = false) -> void:
	_night = night
	_quiet=quiet
	_control.apply_environment(0.0 if night else 1.0,night,true,quiet)
	_water.set_night(night and not quiet)
	for person: Dictionary in _people:
		(person.actor as ElfieActor).visible = not quiet

func _process(_delta: float) -> void:
	if camera_owner == null or _control == null: return
	var paused := bool(camera_owner.observer_presentation_paused())
	_water.set_process(not paused)
	for person: Dictionary in _people:
		(person.actor as ElfieActor).set_process(not paused)
	if paused: return
	var selected := str(camera_owner.get("_active_camera_id"))
	var night := not selected.ends_with("day")
	var quiet := selected.ends_with("quiet")
	if night != _night or quiet!=_quiet: set_phase(night,quiet)


static func add_review_people(parent: Node3D, estate: Node3D) -> Array[Dictionary]:
	# View-only actors exercise the real model and seated pose. They never enter
	# a resident roster, publish semantic events or take physical authority.
	var semantics := preload("res://rooms/estate/estate_semantics.gd").new()
	semantics.build(parent, estate)
	var result: Array[Dictionary] = []
	var bedroom := semantics.anchors.get("dorm-01/chair-01") as Marker3D
	if bedroom != null:
		result.append(_review_person(parent, bedroom, "Bedroom"))
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if extras.get("central_furnishing", "") != "M01_sofa_following_actual_wall": continue
		var seat := _sofa_seat(mesh)
		if seat.is_empty(): continue
		var marker := Marker3D.new()
		parent.add_child(marker)
		marker.global_position = seat.point
		marker.set_meta("kind", "chair")
		marker.set_meta("zone_id", "terrace-01")
		marker.set_meta("interaction_posture", "sitting")
		var floor := semantics.anchors["terrace-01/activity"] as Marker3D
		var forward := (floor.global_position - marker.global_position).normalized()
		marker.set_meta("interaction_transform", Transform3D(Basis(Vector3.UP, atan2(forward.x, forward.z)), marker.global_position))
		result.append(_review_person(parent, marker, "Terrace"))
		break
	return result


static func _review_person(parent: Node3D, marker: Marker3D, label: String) -> Dictionary:
	var actor := load("res://characters/tovren/tovren.tscn").instantiate() as ElfieActor
	actor.set_meta("observer_presentation", true)
	parent.add_child(actor)
	actor.configure("lighting-review-" + label.to_lower(), marker.global_position)
	actor.set_physics_process(false)
	var error := actor.observer_present_anchor(marker, "lighting-review/" + label.to_lower(), "sitting")
	if not error.is_empty(): push_error("Lighting review seat: " + error)
	return {"actor": actor, "label": label, "error": error}


static func _sofa_seat(mesh: MeshInstance3D) -> Dictionary:
	# Take the largest upward upholstery triangle below the backrest. The seat
	# contact comes from actual geometry, rather than an invented floor offset.
	var bounds := mesh.get_aabb()
	var best := 0.0
	var result := {}
	for surface in range(mesh.mesh.get_surface_count()):
		if not "upholstery" in mesh.get_active_material(surface).resource_name.to_lower(): continue
		var arrays := mesh.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		for index in range(0, indices.size(), 3):
			var a := vertices[indices[index]]
			var b := vertices[indices[index + 1]]
			var c := vertices[indices[index + 2]]
			var normal := (b - a).cross(c - a)
			var facing := (normals[indices[index]] + normals[indices[index + 1]] + normals[indices[index + 2]]).normalized()
			var center := (a + b + c) / 3.0
			if normal.length() <= best or facing.y < 0.98: continue
			if center.y < bounds.position.y + 0.25 or center.y > bounds.end.y - 0.20: continue
			best = normal.length()
			result = {"point": mesh.global_transform * center + Vector3.UP * 0.02}
	return result


static func _living_view(estate: Node3D) -> Array:
	var bounds := {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		var assembly := str(extras.get("central_furnishing", ""))
		if assembly not in ["living_reference_sofa", "living_reference_coffee"]: continue
		var box := mesh.global_transform * mesh.get_aabb()
		bounds[assembly] = (bounds[assembly] as AABB).merge(box) if bounds.has(assembly) else box
	if bounds.size() != 2: return []
	var sofa := (bounds.living_reference_sofa as AABB).get_center()
	var table := (bounds.living_reference_coffee as AABB).get_center()
	var forward := table - sofa
	forward.y = 0.0
	var eye := table + forward.normalized() * 4.0
	eye.y = 1.9
	var target := (sofa + table) * 0.5
	target.y = 1.05
	return ["Living", eye, target]
