extends SceneTree
## The action picker must expose every real seat, including shared mesh instances.
const CATALOG := preload("res://rooms/estate/estate_seat_catalog.gd")

func _initialize() -> void: call_deferred("run")

func run() -> void:
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	var world := Node3D.new()
	root.add_child(world)
	world.add_child(estate)
	await process_frame
	var contacts: Array[Dictionary] = []
	CATALOG.new().append(estate, contacts)
	if contacts.size() != 45:
		push_error("Every omitted furniture instance needs a measured contact"); quit(1); return
	var covered := {}
	for contact: Dictionary in contacts:
		covered[(contact.source as Node).get_instance_id()] = true
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		var module := str(extras.get("module", ""))
		if not (module == "central" or (module.begins_with("M") and extras.get("floor") == 2)): continue
		if str(extras.get("kind", "")) not in ["chair", "stool", "ottoman", "floor_cushion"]: continue
		if not covered.has(mesh.get_instance_id()):
			push_error("Real seating instance omitted: " + str(mesh.name)); quit(1); return
	var semantics := preload("res://rooms/estate/estate_semantics.gd").new()
	semantics.build(world, estate)
	var expected := {"central-01":5, "central-02":12, "central-03":12,
		"terrace-01":1, "terrace-02":3, "terrace-03":3, "terrace-04":4,
		"terrace-05":2, "terrace-06":2, "terrace-07":2, "terrace-08":4}
	var counts := {}
	var ids := {}
	for descriptor: Dictionary in semantics.descriptors:
		if ids.has(descriptor.anchor_id):
			push_error("Duplicate furniture target: " + str(descriptor.anchor_id)); quit(1); return
		ids[descriptor.anchor_id] = true
		if descriptor.kind != "chair": continue
		var zone := str(descriptor.zone_id)
		counts[zone] = int(counts.get(zone, 0)) + 1
		var marker := semantics.anchors[descriptor.anchor_id] as Marker3D
		var contact := marker.get_meta("interaction_transform") as Transform3D
		if not contact.origin.is_finite() or marker.global_position.distance_to(contact.origin) > 1.95:
			push_error("Seat has no usable contact: " + str(descriptor.anchor_id)); quit(1); return
	for zone: String in expected:
		if counts.get(zone, 0) != expected[zone]:
			push_error("Missing seats in %s: expected %d, found %d" % [zone, expected[zone], counts.get(zone, 0)])
			quit(1); return
	if semantics.manifest_anchors(32).size() != 92 or semantics.manifest_anchors(32, true).size() != 137:
		push_error("Normal routes and direct-placement inspection targets must stay separate"); quit(1); return
	if semantics.manifest_anchors(32, true).filter(func(a: Dictionary) -> bool: return bool(a.active)).size() != 92:
		push_error("Inspection contacts must stay out of automatic navigation"); quit(1); return
	print("PASS complete seat catalog: ", JSON.stringify(counts))
	world.free()
	quit()
