extends SceneTree
## Reused asset names must not redirect a sleep action to another bed.
const CYCLE := preload("res://runtime/actor/furniture_cycle.gd")
const DUVET := preload("res://runtime/actor/authored_duvet.gd")
var failures := 0

class ContactProbe extends ElfieActor:
	func enter_furniture(_marker: Marker3D, _anchor_id: String) -> String:
		return "contact_probe"

func _initialize() -> void: call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	await check_bed_instances()
	check_skin_frame()
	print("SLEEP_REGRESSIONS failures=", failures)
	quit(1 if failures else 0)

func check_bed_instances() -> void:
	var nest := ModularNest.new()
	var generated := Node3D.new(); generated.name = "Generated"; nest.add_child(generated)
	var estate := Node3D.new(); estate.name = "CompleteEstate"; generated.add_child(estate)
	var actor := ContactProbe.new()
	for room in ["M01", "M02"]:
		for resident in ["A", "B"]:
			var parent := Node3D.new(); estate.add_child(parent)
			var deck := MeshInstance3D.new(); deck.name = "shared_deck"; parent.add_child(deck)
			deck.set_meta("extras", {"module":room, "resident":resident, "piece":"deck"})
			var cover := MeshInstance3D.new(); cover.name = "shared_cover"; parent.add_child(cover)
			cover.set_meta("extras", {"module":room, "resident":resident, "piece":"bed_cover"})
			var marker := Marker3D.new()
			marker.set_meta("source_node", str(deck.name))
			marker.set_meta("furniture_source", deck)
			var runner := CYCLE.new(); runner.actor = actor
			var result: Dictionary = await runner._sleep(marker, room+resident, "sleep-left", nest)
			check(result.reason == "contact_probe", "Sleep did not resolve real bed: "+room+resident)
			check(runner._cloth == cover, "Sleep selected another bed's duvet: "+room+resident)
			runner.free(); marker.free()
	# A missing/stale binding must fail, rather than falling back to a same-name bed.
	var missing := Marker3D.new(); missing.set_meta("source_node", "shared_deck")
	var rejected := CYCLE.new(); rejected.actor = actor
	var result: Dictionary = await rejected._sleep(missing,"missing","sleep-left",nest)
	check(result.reason == "bed_source_unavailable", "Missing bed instance did not fail closed")
	var foreign := MeshInstance3D.new(); missing.set_meta("furniture_source",foreign)
	result = await rejected._sleep(missing,"foreign","sleep-left",nest)
	check(result.reason == "bed_source_unavailable", "Foreign bed instance escaped the target nest")
	foreign.free(); missing.free(); rejected.free()
	actor.free(); nest.free()

func check_skin_frame() -> void:
	var body := Node3D.new(); root.add_child(body)
	var skeleton := Skeleton3D.new(); body.add_child(skeleton)
	skeleton.add_bone("mixamorig_Hips")
	var skin := Skin.new(); skin.add_named_bind("mixamorig_Hips", Transform3D.IDENTITY)
	var mesh := MeshInstance3D.new(); skeleton.add_child(mesh)
	mesh.position = Vector3(0.25, 0.1, -0.2)
	mesh.scale = Vector3(0.9, 1.1, 1.0)
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX)
	var vertices := PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.FORWARD])
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2])
	arrays[Mesh.ARRAY_BONES] = PackedInt32Array([0,0,0,0, 0,0,0,0, 0,0,0,0])
	arrays[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([1,0,0,0, 1,0,0,0, 1,0,0,0])
	var resource := ArrayMesh.new(); resource.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.mesh = resource; mesh.skin = skin
	var points := DUVET.skin_points(body, skeleton)
	for i in range(vertices.size()):
		check(points[i].is_equal_approx(mesh.to_global(vertices[i])), "Duvet fitting ignored the skinned mesh frame")
	body.free()
