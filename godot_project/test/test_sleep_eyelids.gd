extends SceneTree
## Asset-independent regression for sleep phase sampling and eyelid lifetime.
const SLEEP := preload("res://runtime/actor/sleep_cycle.gd")
const NAMES := ["Sleep_EyesQuarter", "Sleep_EyesHalf", "Sleep_EyesThreeQuarter", "Sleep_EyesClosed"]
var failed := false

class DuvetProbe extends RefCounted:
	func sample(_cover: float, _opened: float, _lift: float, _breath: float, _body: float, _defer: bool) -> void: pass
	func commit() -> void: pass

class SleepProbe extends "res://runtime/actor/sleep_cycle.gd":
	func _apply_snapshot(_pose: Dictionary) -> void: pass
	func _blend(_a: Dictionary, _b: Dictionary, _weight: float) -> void: pass
	func _walk(_distance: float, _seconds: float) -> void: pass
	func _reach_duvet(_weight: float) -> void: pass

func _initialize() -> void: call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		failed = true
		push_error(message)

func make_actor() -> ElfieActor:
	var actor := ElfieActor.new()
	actor.install_shared_animations = false
	var visual := Node3D.new(); visual.name = "VisualRoot"; actor.add_child(visual)
	var skeleton := Skeleton3D.new(); visual.add_child(skeleton)
	for suffix: String in ["Hips", "Spine2", "Head"]: skeleton.add_bone("mixamorig_" + suffix)
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
	var mesh := ArrayMesh.new()
	var shapes: Array[Array] = []
	for shape_name: String in NAMES + ["Identity"]:
		mesh.add_blend_shape(shape_name)
		var shape := []; shape.resize(Mesh.ARRAY_MAX)
		shape[Mesh.ARRAY_VERTEX] = arrays[Mesh.ARRAY_VERTEX]
		shapes.append(shape)
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, shapes)
	var lids := MeshInstance3D.new(); lids.name = "Lids"; lids.mesh = mesh; visual.add_child(lids)
	var player := AnimationPlayer.new(); player.name = "AnimationPlayer"; actor.add_child(player)
	var collision := CollisionShape3D.new(); collision.name = "CollisionShape3D"; collision.shape = CapsuleShape3D.new(); actor.add_child(collision)
	root.add_child(actor); actor.set_process(false); actor.set_physics_process(false)
	lids.set_blend_shape_value(4, 0.31)
	return actor

func expect(actor: ElfieActor, expected: Array, label: String) -> void:
	var lids := actor.get_node("VisualRoot/Lids") as MeshInstance3D
	for i in range(4): check(is_equal_approx(lids.get_blend_shape_value(i), float(expected[i])), label + " key " + str(i))
	check(is_equal_approx(lids.get_blend_shape_value(4), 0.31), label + " changed identity shape")

func make_cycle(actor: ElfieActor) -> SleepProbe:
	var cycle := SleepProbe.new(); root.add_child(cycle)
	cycle.mode = "back"; cycle._body = actor; cycle._visual = actor.get_node("VisualRoot")
	cycle._hips = actor._furniture_hips()["skeleton"]
	cycle._poses = {"back": {}}; cycle._duvet = DuvetProbe.new()
	cycle.blanket = MeshInstance3D.new(); cycle.add_child(cycle.blanket)
	cycle._bind_eyes(actor)
	return cycle

func run() -> void:
	var actor := make_actor()
	var runtime: RefCounted = actor.get("_animation_runtime")
	var owner := Node.new(); root.add_child(owner)
	runtime.begin_sleep_eyes(owner)
	var cases := [[-1.0,[0,0,0,0]], [0.125,[0.5,0,0,0]], [0.25,[1,0,0,0]], [0.375,[0.5,0.5,0,0]], [0.5,[0,1,0,0]], [0.625,[0,0.5,0.5,0]], [0.75,[0,0,1,0]], [0.875,[0,0,0.5,0.5]], [1.0,[0,0,0,1]], [2.0,[0,0,0,1]]]
	for item: Array in cases:
		runtime.sample_sleep_eyes(owner, float(item[0]))
		expect(actor, item[1], "closure " + str(item[0]))
	runtime.end_sleep_eyes(owner); expect(actor,[0,0,0,0],"release")

	var cycle := make_cycle(actor)
	for item: Array in [[0.0,[0,0,0,0]], [5.0,[0,0,0,0]], [5.25,[0,1,0,0]], [5.5,[0,0,0,1]], [7.0,[0,0,0,1]], [12.2,[0,1,0,0]], [12.4,[0,0,0,0]], [16.0,[0,0,0,0]], [27.0,[0,0,0,1]]]:
		cycle.sample_bedding(float(item[0])); expect(actor,item[1],"sleep second " + str(item[0]))
	# A reset invalidates the old controller; another old sample cannot re-close.
	runtime.reset_procedural_pose(); cycle.sample_bedding(7.0); expect(actor,[0,0,0,0],"posture reset")
	cycle._bind_eyes(actor); cycle.sample_bedding(7.0)
	runtime.reset_preview_pose(); expect(actor,[0,0,0,0],"preview reset")
	cycle.sample_bedding(7.0); expect(actor,[0,0,0,0],"stale preview sample")
	cycle._bind_eyes(actor); cycle.sample_bedding(7.0)
	runtime.transition_from(runtime.capture_visual_pose()); expect(actor,[0,0,0,0],"exit transition")
	cycle._bind_eyes(actor); cycle.sample_bedding(7.0)
	runtime.cancel_expression(); expect(actor,[0,0,0,0],"expression cancellation")
	cycle._bind_eyes(actor); cycle.sample_bedding(7.0)
	cycle.free(); expect(actor,[0,0,0,0],"controller cancellation/free")

	# Deferred cleanup of a previous cycle must not reset its replacement.
	var old := make_cycle(actor); old.sample_bedding(7.0)
	cycle = make_cycle(actor); cycle.sample_bedding(7.0)
	old.free(); expect(actor,[0,0,0,1],"stale controller cleanup")
	var replacement := make_actor()
	check(cycle.bind_actor(replacement).is_empty(),"same-rig transfer rejected")
	expect(actor,[0,0,0,0],"outgoing actor"); expect(replacement,[0,0,0,0],"incoming actor")
	cycle.sample_bedding(7.0); expect(replacement,[0,0,0,1],"reused actor closes")
	check(cycle.bind_actor(replacement).is_empty(),"same actor rebind rejected")
	expect(replacement,[0,0,0,0],"rebind clears eyes")
	cycle.sample_bedding(7.0)
	var wrong := make_actor(); wrong.species_id = "wrong"
	check(cycle.bind_actor(wrong) == "sleep_species_mismatch","mismatched transfer accepted")
	expect(replacement,[0,0,0,1],"rejected transfer disturbed current actor")
	cycle.free(); expect(replacement,[0,0,0,0],"transferred cycle exit")
	wrong.free(); replacement.free(); owner.free(); actor.free()
	if not failed: print("PASS sleep eyelids: four-key interpolation, phase, reset, cancellation and reuse")
	quit(1 if failed else 0)
