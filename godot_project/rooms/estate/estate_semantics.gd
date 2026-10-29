extends RefCounted

## Stable semantic IDs are bound to nodes from the complete asset itself.
var anchors: Dictionary = {}
var facilities: Dictionary = {}
var zones: Array[Dictionary] = []
var descriptors: Array[Dictionary] = []
var facility_descriptors: Array[Dictionary] = []
var room_floors: Dictionary = {}
var _root: Node3D
var _centers: Dictionary = {}
var _contacts: Dictionary = {}


func build(parent: Node3D, estate: Node3D) -> void:
	_root = Node3D.new()
	_root.name = "EstateInteractionAnchors"
	parent.add_child(_root)
	var meshes := estate.find_children("*", "MeshInstance3D", true, false)
	for mesh: MeshInstance3D in meshes:
		var e := mesh.get_meta("extras", {}) as Dictionary
		var source := str(e.get("source_name", mesh.name))
		var module := str(e.get("module", ""))
		if str(e.get("piece", "")) in ["bed_cover", "chair_cushion"]:
			_contacts[module + ":" + str(e.get("resident", "")) + ":" + str(e["piece"])] = mesh
		if "continuous lower floor" in source:
			room_floors[module] = mesh
			var center := mesh.global_position
			center.y = (mesh.global_transform * mesh.get_aabb()).end.y + 0.02
			_centers[module] = center
			var zone := "dorm-%02d" % int(module.trim_prefix("M"))
			_add_zone(zone, "%02d 真实四人宿舍" % int(module.trim_prefix("M")), "dorm", center)
			_add_facility(zone + "/rest", zone, "rest", "真实床位与书桌", center, ["sleep", "rest", "sit", "work"])
		if "inset terrace walking finish" in source:
			var center := mesh.global_position
			center.y = (mesh.global_transform * mesh.get_aabb()).end.y + 0.02
			var zone := "terrace-%02d" % int(module.trim_prefix("M"))
			_add_zone(zone, "%02d 真实露台活动区" % int(module.trim_prefix("M")), "activity", center)
			_add_anchor(zone + "/activity", zone, "activity", "露台活动区", center, mesh)
			_add_facility(zone + "/social", zone, "social", "真实露台会客区", center, ["social", "rest", "sit"])
		if module == "central" and (source == "Central L1 fitted complete floor" or "complete slab with stair opening" in source or source.begins_with("Central L4 round arrival floor")):
			var level := int(e.get("floor", 1))
			var point := (mesh.global_transform * mesh.get_aabb()).get_center()
			point.y = 0.32 if level == 1 else (4.32 if level == 2 else (7.12 if level == 3 else 9.92))
			var zone := "central-%02d" % level
			_add_zone(zone, "主楼 %d 层" % level, "activity", point)
			_add_anchor(zone + "/activity", zone, "activity", "主楼活动区", point, mesh)
			_add_facility(zone + "/activity", zone, "activity", "主楼真实活动区", point, ["social", "activity"])
	for mesh: MeshInstance3D in meshes:
		var e := mesh.get_meta("extras", {}) as Dictionary
		var module := str(e.get("module", ""))
		var source := str(e.get("source_name", mesh.name))
		if room_floors.has(module):
			var zone := "dorm-%02d" % int(module.trim_prefix("M"))
			var resident := str(e.get("resident", ""))
			var number := "ABCD".find(resident) + 1 if not resident.is_empty() else 0
			var piece := str(e.get("piece", ""))
			if number > 0 and piece in ["deck", "chair_seat"]:
				var center := (mesh.global_transform * mesh.get_aabb()).get_center()
				center.y = (mesh.global_transform * mesh.get_aabb()).end.y + 0.03
				var approach := center.move_toward(_centers[module], 1.6 if piece == "deck" else 0.9)
				approach.y = (_centers[module] as Vector3).y
				var kind := "bed" if piece == "deck" else "chair"
				var marker := _add_anchor("%s/%s-%02d" % [zone, kind, number], zone, kind, "住户 %s %s" % [resident, "床位" if kind == "bed" else "书桌座椅"], approach, mesh)
				marker.set_meta("bed_order", (int(module.trim_prefix("M")) - 1) * 4 + number - 1)
				var contact_mesh := _contacts.get(module + ":" + resident + ":" + ("bed_cover" if kind == "bed" else "chair_cushion"), mesh) as MeshInstance3D
				var contact := (contact_mesh.global_transform * contact_mesh.get_aabb()).get_center()
				contact.y = (contact_mesh.global_transform * contact_mesh.get_aabb()).end.y + 0.02
				_interaction_pose(marker, mesh, contact, "sleeping" if kind == "bed" else "sitting")
		if bool(e.get("door_leaf", false)):
			var connection := str(e.get("connection", ""))
			if _centers.has(connection):
				var zone := "dorm-%02d" % int(connection.trim_prefix("M"))
				var point := (mesh.global_transform * mesh.get_aabb()).get_center()
				var direction: Vector3 = (_centers[connection] as Vector3) - point
				direction.y = 0
				point += direction.normalized() * 0.85
				point.y = (_centers[connection] as Vector3).y
				_add_anchor(zone + "/door", zone, "door", "真实滑动房门", point, mesh)
		if "seven-petal stone and ring-material connector" in source:
			var point := (mesh.global_transform * mesh.get_aabb()).get_center()
			point.y = (mesh.global_transform * mesh.get_aabb()).end.y + 0.02
			_add_zone("courtyard", "完整真实庭院", "activity", point)
			_add_anchor("courtyard/activity", "courtyard", "activity", "庭院七瓣广场", point, mesh)
			_add_facility("courtyard/social", "courtyard", "social", "庭院与草坪", point, ["social", "activity"])
		if source == "Picnic seat plank" or source == "Lakeside bench seat slat":
			var point := (mesh.global_transform * mesh.get_aabb()).get_center()
			point.y = (mesh.global_transform * mesh.get_aabb()).end.y + 0.02
			var id := "courtyard/picnic-seat" if source == "Picnic seat plank" else "courtyard/lakeside-seat"
			var approach := point + Vector3(0, 0, 1 if source == "Picnic seat plank" else -1)
			approach.y = 0.02
			var marker := _add_anchor(id, "courtyard", "chair", "野餐长凳" if source == "Picnic seat plank" else "湖边长凳", approach, mesh)
			_interaction_pose(marker, mesh, point, "sitting")
	zones.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a["zone_id"]) < str(b["zone_id"]))
	print("ESTATE_SEMANTICS anchors=%d zones=%d beds=%d" % [anchors.size(), zones.size(), descriptors.filter(func(a: Dictionary) -> bool: return a["kind"] == "bed").size()])


func _interaction_pose(marker: Marker3D, mesh: MeshInstance3D, point: Vector3, posture: String) -> void:
	var forward := mesh.global_basis.z.normalized()
	marker.set_meta("interaction_transform", Transform3D(Basis(Vector3.UP, atan2(forward.x, forward.z)), point))
	marker.set_meta("interaction_posture", posture)


func _add_zone(id: String, label: String, kind: String, point: Vector3) -> void:
	zones.append({"zone_id": id, "label": label, "kind": kind, "stable_order": zones.size(), "active": true})
	_centers[id] = point


func _add_anchor(id: String, zone: String, kind: String, label: String, point: Vector3, source: Node3D) -> Marker3D:
	var marker := Marker3D.new()
	marker.name = id.replace("/", "__")
	_root.add_child(marker)
	marker.global_position = point
	marker.set_meta("anchor_id", id)
	marker.set_meta("zone_id", zone)
	marker.set_meta("kind", kind)
	marker.set_meta("source_node", str(source.name))
	anchors[id] = marker
	descriptors.append({"anchor_id": id, "zone_id": zone, "kind": kind, "label": label, "stable_order": descriptors.size(), "active": true})
	return marker


func _add_facility(id: String, zone: String, kind: String, label: String, point: Vector3, capabilities: Array) -> void:
	var marker := Marker3D.new()
	marker.name = id.replace("/", "__")
	_root.add_child(marker)
	marker.global_position = point
	marker.set_meta("facility_id", id)
	marker.set_meta("zone_id", zone)
	facilities[id] = marker
	facility_descriptors.append({"facility_id": id, "zone_id": zone, "kind": kind, "label": label, "capabilities": capabilities, "active": true})


func restrict_outdoor_anchors(access: Node3D) -> void:
	for marker: Marker3D in anchors.values():
		if str(marker.get_meta("zone_id")) != "courtyard": continue
		var point := marker.global_position
		marker.set_meta("access_restricted", not access.contains_point(Vector2(point.x, point.z)))


func manifest_anchors(capacity: int) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for descriptor: Dictionary in descriptors:
		var copy := descriptor.duplicate()
		var marker := anchors[str(copy["anchor_id"])] as Marker3D
		if marker.has_meta("bed_order"):
			copy["active"] = int(marker.get_meta("bed_order")) < capacity
		if bool(marker.get_meta("access_restricted", false)):
			copy["active"] = false
		result.append(copy)
	return result


func nearest_zone(point: Vector3) -> String:
	var query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 0.2, point - Vector3.UP * 2.0)
	var excluded: Array[RID] = []
	for actor: Node in _root.get_tree().get_nodes_in_group(&"runtime_elfie_actors"):
		if actor is CollisionObject3D:
			excluded.append((actor as CollisionObject3D).get_rid())
	query.exclude = excluded
	query.hit_from_inside = true
	var hit := _root.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty(): return ""
	var body := hit["collider"] as Node
	var module := str(body.get_meta("estate_module", ""))
	if room_floors.has(module):
		var floor := room_floors[module] as MeshInstance3D
		return ("terrace-%02d" if floor.to_local(point).y > 2.9 else "dorm-%02d") % int(module.trim_prefix("M"))
	if module == "central":
		return "central-%02d" % int(body.get_meta("estate_floor", 1))
	return "courtyard"


func align_approaches(map: RID) -> void:
	# Author a reachable stand point near the actual object; never move an Actor.
	# Do not snap between storeys or replace a disconnected room with another floor.
	for marker: Marker3D in anchors.values():
		if bool(marker.get_meta("access_restricted", false)): continue
		var point := marker.global_position
		var nearest := NavigationServer3D.map_get_closest_point(map, point)
		var limit := 2.0 if str(marker.get_meta("kind")) == "activity" else 0.5
		# Outdoor seats must approach from their platform, not adjacent lawn.
		# Keep the existing contact-distance and same-storey checks below.
		if str(marker.get_meta("zone_id")) == "courtyard" and str(marker.get_meta("kind")) == "chair":
			limit = 1.0
		var found := _valid_approach(marker, point, nearest, limit)
		var best := nearest.distance_to(point) if found else INF
		# Tables can have navigable tops closer to a room's geometric centre
		# than its floor. Search only the nearby authored floor, never snap up
		# onto that furniture or down to a different storey.
		for ring in range(1, int(ceil(limit / 0.25)) + 1):
			for angle in range(16):
				var radians := TAU * float(angle) / 16.0
				var sample := point + Vector3(cos(radians), 0, sin(radians)) * minf(ring * 0.25, limit)
				var candidate := NavigationServer3D.map_get_closest_point(map, sample)
				var distance := candidate.distance_to(point)
				if distance < best and _valid_approach(marker, point, candidate, limit):
					nearest = candidate
					best = distance
					found = true
		if found:
			marker.global_position = nearest


func _valid_approach(marker: Marker3D, origin: Vector3, candidate: Vector3, limit: float) -> bool:
	if absf(candidate.y - origin.y) > 0.16 or candidate.distance_to(origin) > limit:
		return false
	if marker.has_meta("interaction_transform"):
		var contact := marker.get_meta("interaction_transform") as Transform3D
		if contact.origin.distance_to(candidate) > 1.95:
			return false
	return true
