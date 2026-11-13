extends SceneTree
## Real rigs and production acquisition/release, without loading the estate.
const SEAT := preload("res://runtime/actor/direct_seat_cycle.gd")
const CLIPS := preload("res://runtime/actor/chair_clip_sequence.gd")
const CONTACT := preload("res://runtime/actor/furniture_contact.gd")
const RUNTIME := preload("res://runtime/actor/actor_animation_runtime.gd")
const FROZEN := ["pose_thinking", "pose_victory", "pose_thumbs_up", "pose_hands_on_hips"]
var _failures := 0
var _floor_failures := 0
var _floor_failure_kinds := {}

func _initialize() -> void: call_deferred("run")

func check(ok: bool, message: String, floor_check: bool = false) -> bool:
	if not ok:
		_failures += 1
		if floor_check: _floor_failures += 1
		push_error(message)
	return ok

func finish_report(label: String) -> void:
	print("GROUNDING_RESULT ", JSON.stringify({"test":label,"failures":_failures,
		"floor_failures":_floor_failures,"floor_failure_kinds":_floor_failure_kinds,
		"non_floor_failures":_failures-_floor_failures}))
	if _failures == 0: print("PASS ",label)
	quit(1 if _failures > 0 else 0)

func make_actor(species: String, position: Vector3 = Vector3.ZERO) -> ElfieActor:
	var actor := (load("res://characters/%s/%s.tscn" % [species,species]) as PackedScene).instantiate() as ElfieActor
	root.add_child(actor)
	actor.configure("restore-" + species, position)
	actor.set_process(false); actor.set_physics_process(false)
	return actor

func idle_start(actor: ElfieActor) -> void:
	var runtime: RefCounted = actor.get("_animation_runtime")
	runtime.cancel_expression()
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	player.playback_active = true
	player.play("idle", 0.0); player.seek(0.0, true); player.advance(0.0)

func check_frozen_grounding(actor: ElfieActor) -> void:
	var runtime: RefCounted = actor.get("_animation_runtime")
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var visual := actor.get_node("VisualRoot") as Node3D
	idle_start(actor)
	var standing := visual.transform
	var actor_frame := actor.global_transform
	for pose: String in FROZEN:
		# Read the source clip directly, without the runtime contact overlay.
		player.playback_active = true
		player.play(pose, 0.0)
		player.seek(player.get_animation(pose).length * float(RUNTIME.PREVIEW_POSE_FRAME_RATIOS[pose]), true)
		player.playback_active = false
		var raw_feet := CONTACT.sole_y(actor) - actor.global_position.y
		var raw_bones: Array = runtime.capture_visual_pose()["bones"]
		print("FROZEN_SOURCE_GROUNDING ", JSON.stringify({"species":actor.species_id,"clip":pose,"relative_feet_y":raw_feet}))
		idle_start(actor)
		for exit_kind: String in ["idle", "walking", "nod_head", "cancel", "reset"]:
			check(actor.play_runtime_expression(pose), "Frozen grounding rejected " + pose)
			runtime.advance(0.5)
			check(absf(CONTACT.sole_y(actor)-actor.global_position.y) < 0.001, "Frozen sole not grounded: " + actor.species_id + " " + pose)
			check(actor.global_transform.is_equal_approx(actor_frame), "Frozen grounding moved physics body")
			for bone: Dictionary in raw_bones:
				var skeleton: Skeleton3D = bone["skeleton"]
				check(skeleton.get_bone_pose_position(bone["bone"]).is_equal_approx(bone["position"]), "Grounding changed source bone position")
				check(skeleton.get_bone_pose_rotation(bone["bone"]).is_equal_approx(bone["rotation"]), "Grounding changed source bone rotation")
			if exit_kind == "cancel": runtime.cancel_expression()
			elif exit_kind == "reset": runtime.reset_procedural_pose()
			else:
				check(actor.play_runtime_expression(exit_kind), "Grounding exit rejected")
				runtime.advance(0.5)
			check(visual.transform.is_equal_approx(standing), "Frozen offset leaked after " + exit_kind)
			idle_start(actor)
	# Direct frozen-to-frozen replacement must not accumulate the prior offset.
	for pose: String in FROZEN + FROZEN:
		check(actor.play_runtime_expression(pose), "Frozen replacement rejected")
		runtime.advance(0.5)
		check(absf(CONTACT.sole_y(actor)-actor.global_position.y) < 0.001, "Frozen replacement drifted")
	idle_start(actor)
	check(visual.transform.is_equal_approx(standing), "Repeated poses changed standing frame")
	# A new expression may arrive before the furniture exit blend has finished.
	var source: Dictionary = runtime.capture_visual_pose()
	var source_visual: Transform3D = source["visual"]
	source_visual.origin.y += 0.12
	source["visual"] = source_visual
	runtime.transition_from(source)
	check(actor.play_runtime_expression("pose_thinking"), "Blend replacement rejected")
	var frozen_bones: Array = runtime.capture_visual_pose()["bones"]
	for tick in range(10):
		runtime.advance(0.1)
		check(absf(CONTACT.sole_y(actor)-actor.global_position.y) < 0.001, "Exit blend lost frozen contact")
	for bone: Dictionary in frozen_bones:
		var skeleton: Skeleton3D = bone["skeleton"]
		check(skeleton.get_bone_pose_position(bone["bone"]).is_equal_approx(bone["position"]), "Exit blend replaced frozen position")
		check(skeleton.get_bone_pose_rotation(bone["bone"]).is_equal_approx(bone["rotation"]), "Exit blend replaced frozen rotation")
	idle_start(actor)
	check(visual.transform.is_equal_approx(standing), "Exit blend retained frozen offset")

func check_clips(actor: ElfieActor, stage: String, reference: Dictionary = {}) -> Dictionary:
	actor.set_process(false); actor.set_physics_process(false)
	idle_start(actor)
	var runtime: RefCounted = actor.get("_animation_runtime")
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var samples := {}
	var clips: Array = RUNTIME.SHARED_ANIMATIONS.keys()
	clips.append_array(["nod_head", "shake_head"])
	check(reference.is_empty() or reference.size() == clips.size(), "Incomplete fresh reference: " + stage)
	for clip: String in clips:
		if not check(actor.play_runtime_expression(clip), "Rejected " + clip): continue
		runtime.advance(0.5)
		var feet := CONTACT.sole_y(actor)
		var relative := feet - actor.global_position.y
		var hips := actor._furniture_hips()
		var expected := float(reference.get(clip, relative))
		var floor_ok := relative >= -0.04 and relative <= 0.10
		var floor_classification := "within_floor_band"
		if not floor_ok:
			if reference.is_empty(): floor_classification = "fresh_baseline_deviation"
			elif not reference.has(clip): floor_classification = "missing_reference"
			elif (expected < -0.04 or expected > 0.10) and absf(relative-expected) < 0.001:
				floor_classification = "unchanged_baseline_deviation"
			else: floor_classification = "post_furniture_deviation"
		print("RESTORED_GROUNDING ", JSON.stringify({"species":actor.species_id,"stage":stage,"clip":clip,
			"actor_y":actor.global_position.y,"visual_y":actor.get_node("VisualRoot").position.y,
			"hips_y":hips.skeleton.get_bone_pose_position(hips.bone).y,"feet_y":feet,"relative_feet_y":relative,
			"lowest_foot_pivot_y":ActorAppearance._foot_contact_y(actor.get_node("VisualRoot")),
			"reference_feet_y":expected,"restoration_delta_y":relative-expected,"has_reference":reference.has(clip),
			"frozen_floor_ok":floor_ok if clip in FROZEN else null,
			"floor_classification":floor_classification if clip in FROZEN else null}))
		check(is_finite(relative), "No skinned feet: " + clip)
		if not reference.is_empty():
			check(reference.has(clip) and absf(relative-expected) < 0.025, "Furniture changed foot height: " + actor.species_id + " " + stage + " " + clip)
		if clip in FROZEN:
			if not floor_ok:
				_floor_failure_kinds[floor_classification] = int(_floor_failure_kinds.get(floor_classification,0)) + 1
			check(floor_ok, "Frozen feet missed standing floor: " + actor.species_id + " " + stage + " " + clip + " " + floor_classification, true)
			var cursor := player.current_animation_position
			var duration := player.get_animation(clip).length * 2.0 + 0.5
			for tick in range(60):
				runtime.play("idle"); runtime.advance(duration / 60.0)
			check(player.current_animation == clip and not player.playback_active, "Frozen pose released")
			check(is_equal_approx(player.current_animation_position,cursor), "Frozen clock moved")
			check(absf(CONTACT.sole_y(actor)-feet) < 0.001, "Frozen feet drifted")
		samples[clip] = relative
	return samples

func run() -> void:
	for species: String in ["tovren", "saevi"]:
		var actor := make_actor(species)
		check_frozen_grounding(actor)
		var player := actor.get_node("AnimationPlayer") as AnimationPlayer
		var visual := actor.get_node("VisualRoot") as Node3D
		var original := player.get_animation_library("")
		var previous_chair := AnimationLibrary.new()
		player.add_animation_library("chair",previous_chair)
		var baseline := check_clips(actor,"fresh")
		if not check(baseline.size() == 20, "Incomplete fresh actor sequence"):
			actor.free(); finish_report("seat animation restoration"); return
		idle_start(actor)
		var standing := visual.transform
		var locomotion := CLIPS.locomotion_for(actor)
		var seated := CLIPS.library_for(actor)
		for exit_kind: String in ["completed", "cancelled", "tree_exit"]:
			var seat := SEAT.new(); root.add_child(seat); seat.set_process(false); seat.actor = actor
			seat._install_seat_animations(locomotion,seated)
			check(player.get_animation("idle") == locomotion.get_animation("idle"), "Seat lost retargeted idle")
			check(player.get_animation("walking") == locomotion.get_animation("walking"), "Seat lost retargeted walking")
			idle_start(actor); CONTACT.ground(actor,actor.global_position.y)
			if exit_kind == "cancelled": actor.cancel_furniture_cycle("grounding_test")
			if exit_kind == "tree_exit": seat.free()
			else: seat._finish()
			check(player.get_animation_library("") == original, "Original default library not restored: " + exit_kind)
			check(player.get_animation_library("chair") == previous_chair, "Previous chair library not restored")
			check(visual.transform.is_equal_approx(standing), "Standing visual frame not restored")
			check_clips(actor,exit_kind,baseline)
			idle_start(actor)
			if is_instance_valid(seat):
				# Delayed deletion must not touch a newer seat's library/ground frame.
				var newer := SEAT.new(); root.add_child(newer); newer.set_process(false); newer.actor = actor
				newer._install_seat_animations(locomotion,seated)
				idle_start(actor); CONTACT.ground(actor,actor.global_position.y)
				var active_library := player.get_animation_library("")
				var active_visual := visual.transform
				seat.free()
				check(player.get_animation_library("") == active_library and visual.transform.is_equal_approx(active_visual), "Late exit overwrote replacement")
				newer._finish(); newer.free()
		player.remove_animation_library("chair")
		var final := SEAT.new(); root.add_child(final); final.actor = actor; final.set_process(false)
		final._install_seat_animations(locomotion,seated); final._finish(); final.free()
		check(not player.has_animation_library("chair"), "Temporary chair library leaked")
		actor.free()
	finish_report("seat animation ownership: complete/cancel/exit/reuse, both rigs and all 20 expressions")
