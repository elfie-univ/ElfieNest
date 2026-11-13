extends SceneTree
## Production seat grouping and signed swivel route, including an intermediate obstacle.
const SEAT := preload("res://runtime/actor/direct_seat_cycle.gd")
var failures := 0

class ActorProbe extends ElfieActor:
	var available := true
	func _init() -> void:
		# Base @onready bindings run even though this probe overrides _ready().
		var visual := Node3D.new(); visual.name = "VisualRoot"; add_child(visual)
		var collision := CollisionShape3D.new(); collision.name = "CollisionShape3D"
		collision.shape = CapsuleShape3D.new(); collision.disabled = true; add_child(collision)
		var player := AnimationPlayer.new(); player.name = "AnimationPlayer"; add_child(player)
	func _ready() -> void:
		set_process(false); set_physics_process(false)
	func cycle_available() -> bool: return available

class SwivelProbe extends Node3D:
	var excluded: Array[RID] = []
	var last_obstacle := ""
	func _clear(_frame: Transform3D, _passenger: CharacterBody3D) -> bool: return true

class MotionProbe extends RefCounted:
	var seated_shapes: Array[Shape3D] = []
	var start_frame := Transform3D.IDENTITY
	var end_frame := Transform3D.IDENTITY
	var rise_scale := 1.0
	var arc_clearance := 0.0
	var last_collider: Node
	var last_obstacle := ""

func _initialize() -> void: call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func plank(parent: Node3D, name: String, z: float) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = name
	var box := BoxMesh.new(); box.size = Vector3(3.0,0.11,0.135)
	node.mesh = box
	parent.add_child(node)
	node.position = Vector3(-27,0.55,z)
	return node

func run() -> void:
	var geometry := Node3D.new(); root.add_child(geometry)
	var source := plank(geometry,"Picnic seat plank",14.4)
	# Reverse order forces connected grouping to revisit candidates.
	plank(geometry,"Picnic seat plank_002",14.1)
	plank(geometry,"Picnic seat plank_001",14.25)
	for z: float in [11.9,11.75,11.6]: plank(geometry,"Picnic seat plank_"+str(z).replace(".",""),z)
	var bounds: AABB = SEAT.bench_bounds(geometry,source)
	expect(absf(bounds.get_center().z-14.25) < 0.001, "Picnic grouped the opposite bench through the table")
	expect(absf(bounds.size.z-0.435) < 0.001, "Picnic lost adjacent seat boards")
	expect(absf(bounds.get_center().z+0.9-15.15) < 0.001, "Waiting point is inside the picnic table")
	geometry.free()
	var actor := ActorProbe.new(); root.add_child(actor)
	expect(actor._visual_root != null and actor._collision_shape != null and actor._animation_player != null,
		"Synthetic actor did not initialize the base scene bindings")
	var swivel := SwivelProbe.new(); root.add_child(swivel)
	var seat := SEAT.new(); root.add_child(seat); seat.set_process(false)
	seat.actor = actor; seat.swivel = swivel; seat.open_angle = PI
	expect(absf(seat.opening_target(PI)-PI) < 0.00001, "Fresh opening lost its chosen half-turn direction")
	swivel.rotation.y = -PI
	expect(absf(seat.opening_target(PI)-swivel.rotation.y) < 0.00001, "Reused half-turn requested a full revolution")
	expect(absf(seat.desk_target()-(swivel.rotation.y-PI)) < 0.00001, "Canonical Euler angle reversed the validated desk path")
	swivel.rotation.y = 0.0
	expect(absf(seat.exit_target()-PI) < 0.00001, "Exit did not reverse the desk path")
	swivel.rotation.y = -PI
	var motion := MotionProbe.new(); seat.motion = motion
	var hull := BoxShape3D.new(); hull.size = Vector3.ONE*0.1
	hull.set_meta("body_region","test_foot")
	motion.seated_shapes.append(hull)
	motion.end_frame.origin = Vector3(0,1,-1)
	var obstacle := StaticBody3D.new(); root.add_child(obstacle)
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new(); box.size = Vector3.ONE*0.2
	collision.shape = box; obstacle.add_child(collision)
	# +PI -> 0 crosses +X; its endpoints and the opposite semicircle are clear.
	obstacle.position = Vector3(1,1,0)
	await physics_frame; await physics_frame
	expect(not await seat.seated_desk_clear(), "Endpoint-only fitting missed an intermediate drawer collision")
	expect(motion.last_obstacle.contains("test_foot"), "Turn preflight did not identify the colliding body region")
	var opened_frame := swivel.global_transform
	var seated_frame := motion.end_frame
	expect(await seat.fit_seated_turn(), "Did not try the other clear semicircle for the same pose")
	expect(absf(seat._desk_turn_delta-PI) < 0.00001, "Selected the obstructed negative half-turn")
	expect(swivel.global_transform.is_equal_approx(opened_frame) and motion.end_frame.is_equal_approx(seated_frame),
		"Route selection changed the physical chair or seating offset")
	swivel.rotation.y = 0.0
	expect(absf(seat.exit_target()+PI) < 0.00001, "Positive desk route did not exit on its reverse")
	swivel.global_transform = opened_frame
	obstacle.position = Vector3(-1,1,0)
	await physics_frame; await physics_frame
	expect(await seat.fit_seated_turn({"turn_delta":PI}), "Blocked cached route prevented trying the opposite semicircle")
	expect(absf(seat._desk_turn_delta+PI) < 0.00001, "Cached route was accepted without revalidation")
	swivel.rotation.y = 0.0
	expect(absf(seat.exit_target()-PI) < 0.00001, "Negative desk route did not exit on its reverse")
	swivel.global_transform = opened_frame
	var other := StaticBody3D.new(); root.add_child(other)
	var other_shape := CollisionShape3D.new(); other_shape.shape = box; other.add_child(other_shape)
	other.position = Vector3(1,1,0)
	await physics_frame; await physics_frame
	expect(not await seat.fit_seated_turn(), "Both obstructed semicircles were accepted")
	actor.available = false
	expect(not await seat.fit_seated_turn(), "Cancelled turn preflight continued")
	seat.free(); other.free(); obstacle.free(); swivel.free(); actor.free()
	if failures == 0: print("PASS connected seat boards, reused signed angle, complete passenger turn collision and cancellation")
	quit(1 if failures else 0)
