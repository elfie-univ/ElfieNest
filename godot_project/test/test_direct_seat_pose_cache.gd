extends SceneTree
const MOTION := preload("res://runtime/actor/direct_seat_motion.gd")
const CLIPS := preload("res://runtime/actor/chair_clip_sequence.gd")
const HANDS := preload("res://runtime/actor/direct_seated_arm_pose.gd")
const HULLS := preload("res://runtime/actor/furniture_seated_collision.gd")
const CONTACT := preload("res://runtime/actor/furniture_contact.gd")
const PROFILE := preload("res://nest/furniture/layouts/bedroom/direct-seat.tres")
func _initialize() -> void:
	create_timer(25.0).timeout.connect(func() -> void: push_error("Seated regression timed out"); quit(1))
	call_deferred("run")
func check(ok: bool, message: String) -> bool:
	if not ok: push_error(message); quit(1)
	return ok
func run() -> void:
	var actor := preload("res://characters/tovren/tovren.tscn").instantiate() as ElfieActor
	root.add_child(actor)
	actor.configure("cache",Vector3.ZERO)
	actor._furniture_motion._cycle_deadline = Time.get_ticks_msec()+90000
	var library := CLIPS.library_for(actor)
	HANDS.bake(library.get_animation("seated_idle"),actor,PROFILE.get_meta("hand_rest"))
	(actor.get_node("AnimationPlayer") as AnimationPlayer).add_animation_library("chair",library)
	var first := MOTION.new()
	var contact := Transform3D(Basis.IDENTITY,Vector3(0,0.7,0))
	var entry := Transform3D(Basis.IDENTITY,Vector3(0,0,0.35))
	var started := Time.get_ticks_msec()
	if not check((await first.bind(actor,contact,entry,PROFILE,Callable(HULLS,"shapes"),Callable(CONTACT,"butt_point"))).is_empty(),"Initial pose preparation failed"): return
	print("SEATED_CACHE_FIRST_MS ",Time.get_ticks_msec()-started)
	var shape: Shape3D = first.pose_shapes[8][0]
	var second := MOTION.new()
	started = Time.get_ticks_msec()
	if not check((await second.bind(actor,contact,entry,PROFILE,Callable(HULLS,"shapes"),Callable(CONTACT,"butt_point"))).is_empty(),"Repeat pose preparation failed"): return
	print("SEATED_CACHE_REPEAT_MS ",Time.get_ticks_msec()-started)
	if not check(second.pose_shapes[8][0] == shape,"Repeat playback rebuilt identical skinned collision poses"): return
	# A different body must not accidentally reuse the previous hulls.
	(actor.get_node("VisualRoot") as Node3D).scale *= 1.08
	var changed := MOTION.new()
	if not check((await changed.bind(actor,contact,entry,PROFILE,Callable(HULLS,"shapes"),Callable(CONTACT,"butt_point"))).is_empty(),"Changed-body preparation failed"): return
	if not check(changed.pose_shapes[8][0] != shape,"Body scale change reused stale collision data"): return
	actor.free()
	print("PASS repeated seated pose reuse and body-change invalidation")
	quit(0)
