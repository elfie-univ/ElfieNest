extends SceneTree
func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok
func run() -> void:
	var world := Node3D.new(); root.add_child(world)
	var estate := load("res://nest/assembly/estate.tscn").instantiate() as Node3D
	world.add_child(estate)
	if not require(estate.get_meta("split_runtime_ready", false), "Split runtime bindings must be formal assembly resources"): return
	var semantics := preload("res://nest/spatial/estate_semantics.gd").new()
	semantics.build(world, estate)
	if not require(semantics.room_floors.size() == 8, "Eight split rooms must retain independent semantics"): return
	var beds := 0
	var chairs := 0
	for anchor: String in semantics.anchors:
		if "/bed-" in anchor: beds += 1
		if "/chair-" in anchor: chairs += 1
	if not require(beds == 32 and semantics.zones.size() == 21, "All 32 beds and 21 zones must bind"): return
	if not require(chairs == 32, "All 32 bedroom chair instances must retain independent interaction identities"): return
	var bench: Marker3D = semantics.anchors["courtyard/lakeside-seat"]
	var contact: Transform3D = bench.get_meta("interaction_transform")
	var approach := bench.global_position - contact.origin
	approach.y = 0.0
	if not require(approach.normalized().dot(contact.basis.z.normalized()) > 0.99, "Bench approach must follow its actual facing side"): return
	var doors := 0
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if bool((mesh.get_meta("extras", {}) as Dictionary).get("door_leaf", false)): doors += 1
	if not require(doors == 8, "Eight bedroom door leaves must bind independently"): return
	var restored: Dictionary = estate.get_meta("runtime_bindings", {})
	if not require(int(restored.get("lights", 0)) == estate.find_children("*", "Light3D", true, false).size() and int(restored.lights) >= 272, "Every current light must retain an independent control"): return
	print("PASS split runtime: beds=", beds, " zones=", semantics.zones.size(), " anchors=", semantics.anchors.size(), " lights=", restored.lights)
	world.free(); quit(0)
