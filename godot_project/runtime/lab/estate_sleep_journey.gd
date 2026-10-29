extends Node3D
## Local same-actor handoff through the existing furniture contact API.
## The hidden rig prepares the approved poses; it never replaces the traveller.

const SLEEP := preload("res://runtime/lab/estate_sleep_review.gd")
const SKIN_GUARD := preload("res://runtime/lab/chair_seated_collision.gd")
var actor: ElfieActor
var probe: ElfieActor
var review: Node3D
var effects: Node3D
var goal_position := Vector3.ZERO
var contact: Marker3D
var active := false
var mode := "back"
var anchor_id := ""
var _entry: Dictionary = {}
var _pose_queries: Dictionary = {}
var _excluded: Array[RID] = []
var _actor_process := true


func prepare(body: ElfieActor, marker: Marker3D, duvet: MeshInstance3D, geometry: Node3D, physics: Node3D, id: String) -> String:
	var error := ElfieActor.furniture_marker_error(marker)
	if not error.is_empty(): return error
	if str(marker.get_meta("interaction_posture")) != "sleeping": return "not_a_sleep_contact"
	if body.scene_file_path.is_empty() or duvet == null: return "missing_original_sleep_asset"
	actor = body
	anchor_id = id
	probe = (load(body.scene_file_path) as PackedScene).instantiate() as ElfieActor
	probe.visible = false
	add_child(probe)
	probe.remove_from_group(&"runtime_elfie_actors")
	probe.collision_layer = 0
	probe.collision_mask = 0
	probe.set_physics_process(false)
	probe.configure("hidden-sleep-contact-measurement", marker.global_position)
	error = probe.enter_furniture(marker, id)
	if not error.is_empty(): return error
	review = SLEEP.new()
	add_child(review)
	review.bind(probe, duvet, null)
	review.set_process(false)
	var standing: Transform3D = review.get("_standing")["visual"]
	goal_position = Vector3(standing.origin.x, marker.global_position.y, standing.origin.z)
	contact = Marker3D.new()
	add_child(contact)
	contact.global_position = goal_position
	# A measured bedside approach to the SAME authored bed/contact, not a new
	# semantic bed or a replacement world anchor.
	for key: StringName in marker.get_meta_list(): contact.set_meta(key, marker.get_meta(key))
	_excluded = [actor.get_rid(), probe.get_rid()]
	var bed_names: Dictionary = {}
	var shells: Array[MeshInstance3D] = []
	var shell: MeshInstance3D
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var extra := mesh.get_meta("extras", {}) as Dictionary
		if extra.get("module") != "M01" or extra.get("resident") != "A" or extra.get("assembly") != "bed": continue
		bed_names[str(mesh.name)] = true
		if extra.get("piece") in ["shell", "rolled_lip", "deck"]: shells.append(mesh)
		if extra.get("piece") == "shell": shell = mesh
	for obstacle: StaticBody3D in physics.find_children("*", "StaticBody3D", true, false):
		if bed_names.has(str(obstacle.get_meta("source_node", ""))): _excluded.append(obstacle.get_rid())
	if shell == null or shells.size() != 3: return "missing_original_bed_shell"
	effects = preload("res://runtime/lab/estate_event_effects.gd").new()
	add_child(effects)
	var bounds := shell.get_aabb()
	var points := PackedVector3Array()
	var crown := PackedVector3Array()
	for part: MeshInstance3D in shells:
		var frame := shell.global_transform.affine_inverse() * part.global_transform
		bounds = bounds.merge(frame * part.get_aabb())
		for surface in range(part.mesh.get_surface_count()):
			for vertex: Vector3 in part.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]:
				points.append(frame * vertex)
				if str((part.get_meta("extras", {}) as Dictionary).get("piece")) == "rolled_lip": crown.append(frame * vertex)
	effects.configure_bed(shell.global_transform, bounds, points, crown)
	review.set_mode("back")
	review.sample_bedding(1.5)
	return ""


func validate_pose_path(value: String) -> String:
	if not _pose_queries.has(value):
		review.bind_actor(probe)
		review.set_mode(value)
		var samples: Array[Dictionary] = []
		for seconds: float in [1.5, 2.3, 3.3, 4.5, 7.0, 13.0, 15.0, 16.0]:
			review.sample_bedding(seconds)
			for shape: Shape3D in SKIN_GUARD.shapes(probe):
				samples.append({"shape": shape, "transform": probe.global_transform, "stage": review.get("animation_stage")})
		_pose_queries[value] = samples
		review.sample_bedding(1.5)
	var space := get_world_3d().direct_space_state
	for sample: Dictionary in _pose_queries[value]:
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = sample["shape"]
		query.transform = sample["transform"]
		query.collision_mask = actor.collision_mask
		query.exclude = _excluded
		query.margin = 0.0
		var hit := space.intersect_shape(query, 1)
		if not hit.is_empty():
			var obstacle := hit[0]["collider"] as Node
			return "sleep path blocked at %s by %s" % [sample["stage"], str(obstacle.get_meta("source_node", obstacle.name))]
	return ""


func begin(value: String) -> String:
	if active: return "bed_already_in_use"
	if actor.global_position.distance_to(goal_position) > 0.05: return "bedside_not_physically_reached"
	var error := validate_pose_path(value)
	if not error.is_empty(): return error
	review.bind_actor(probe)
	review.set_mode(value)
	review.sample_bedding(1.5)
	var visual := actor.get_node("VisualRoot") as Node3D
	var standing: Transform3D = review.get("_standing")["visual"]
	if visual.global_position.distance_to(standing.origin) > 0.15: return "bedside_visual_contact_mismatch"
	error = actor.enter_furniture(contact, anchor_id)
	if not error.is_empty(): return error
	error = review.bind_actor(actor)
	if not error.is_empty():
		actor.leave_furniture()
		return error
	# enter_furniture preserves the current WORLD visual pose during the local
	# contact transfer. Continue that blend; never show the prepared end pose.
	_entry = review.call("_snapshot")
	_actor_process = actor.is_processing()
	actor.set_process(false)
	active = true
	mode = value
	return ""


func blend_entry(amount: float) -> void:
	review.call("_blend", _entry, review.get("_standing"), amount)


func sample(seconds: float) -> void:
	review.sample_bedding(seconds)


func finish() -> String:
	if not active: return "bed_not_in_use"
	# Preserve the reached standing pose while the existing furniture exit
	# checks the real standing capsule against the current world.
	if not actor.leave_furniture():
		var collision: CollisionShape3D = actor.get("_collision_shape")
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = collision.shape
		query.transform = (actor.get("_furniture_exit_transform") as Transform3D) * collision.transform
		query.collision_mask = actor.collision_mask
		query.exclude = [actor.get_rid()]
		query.margin = 0.001
		var hits := get_world_3d().direct_space_state.intersect_shape(query, 1)
		if not hits.is_empty():
			var obstacle: Node = hits[0]["collider"]
			return "bed_exit_blocked: " + str(obstacle.get_meta("source_node", obstacle.name))
		return "bed_exit_blocked"
	actor.set_process(_actor_process)
	review.bind_actor(probe)
	effects.preview_cover(6.0)
	active = false
	return ""
