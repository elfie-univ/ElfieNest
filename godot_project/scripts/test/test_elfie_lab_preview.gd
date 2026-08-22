extends SceneTree

const CONTROLLER_SCRIPT := preload("res://lab_preview_controller.gd")
const ACTOR_SCRIPT := preload("res://characters/shared/elfie_actor.gd")
const DOG_SCENE := preload("res://characters/dog/dog.tscn")
const FOX_SCENE := preload("res://characters/fox/fox.tscn")

var _failed := false
var _created_actors: Array[Node3D] = []


class FakePreviewActor extends Node3D:
	var configure_calls := 0
	var preview_intents: Array[Dictionary] = []


	func configure(_identity: String, _position: Vector3, _appearance: Dictionary) -> void:
		configure_calls += 1


	func visual_bounds() -> AABB:
		return AABB(Vector3(-0.4, 0.0, -0.25), Vector3(0.8, 1.8, 0.5))


	func preview_focus_point(target: String) -> Vector3:
		return Vector3(0.0, 1.55 if target == "head" else 0.9, 0.0)


	func play_preview_intent(intent: Dictionary) -> bool:
		if String(intent.get("type", "")) != "motion":
			return false
		if not [
			"nod_head",
			"shake_head",
			"pose_hands_on_hips",
			"pose_thinking",
			"pose_victory",
			"pose_thumbs_up",
			"pose_waving",
		].has(String(intent.get("motion", ""))):
			return false
		preview_intents.append(intent.duplicate(true))
		return true


func _init() -> void:
	call_deferred("_run_contract")


func _run_contract() -> void:
	var characters := Node3D.new()
	var camera := Camera3D.new()
	root.add_child(characters)
	root.add_child(camera)
	var controller := CONTROLLER_SCRIPT.new()
	root.add_child(controller)
	controller.setup(
		characters,
		camera,
		{"fox": PackedScene.new()},
		Callable(self, "_create_actor"),
	)

	var configured: Dictionary = controller.handle_message(_message("configure", "req-1", {
		"elfie_id": "fox-1",
		"species_id": "fox",
		"spec_revision": 7.0,
		"appearance": {},
	}))
	_require(_is_completed(configured), "Initial configure did not complete")
	_require(characters.get_child_count() == 1, "Initial configure did not create exactly one actor")
	var actor := characters.get_child(0) as FakePreviewActor
	_require(actor.configure_calls == 1, "Initial configure did not configure the actor once")
	var full_body_camera_size := camera.size
	var head_focus: Dictionary = controller.handle_message(
		_message("focus", "head-frame", {"target": "head"})
	)
	var expected_bust_height := 1.8 * 0.62
	var expected_bust_center_y := 1.8 - expected_bust_height * 0.5
	_require(_is_completed(head_focus), "Head focus did not complete")
	_require(
		absf(camera.global_position.y - expected_bust_center_y) < 0.001,
		"Head focus did not center the head-to-elbow region",
	)
	_require(
		camera.size < full_body_camera_size,
		"Head focus retained the full-body camera size",
	)
	var upper_body_camera_size := camera.size
	var portrait_focus: Dictionary = controller.handle_message(
		_message("focus", "portrait-frame", {"target": "portrait"})
	)
	_require(_is_completed(portrait_focus), "Portrait focus did not complete")
	_require(
		camera.size < upper_body_camera_size,
		"Portrait focus retained the upper-body camera size",
	)

	var v9_characters := Node3D.new()
	var v9_camera := Camera3D.new()
	v9_camera.set_meta(&"v9_render_profile", true)
	var v9_controller := CONTROLLER_SCRIPT.new()
	root.add_child(v9_characters)
	root.add_child(v9_camera)
	root.add_child(v9_controller)
	v9_controller.setup(
		v9_characters,
		v9_camera,
		{"fox": PackedScene.new()},
		Callable(self, "_create_actor"),
	)
	_require(
		_is_completed(v9_controller.handle_message(_message("configure", "v9-configure", {
			"elfie_id": "fox-v9",
			"species_id": "fox",
			"spec_revision": 8,
			"appearance": {},
		}))),
		"V9 preview configure did not complete",
	)
	var v9_actor := v9_characters.get_child(0) as FakePreviewActor
	var v9_bounds := v9_actor.visual_bounds()
	var v9_full_body_distance := v9_camera.global_position.distance_to(v9_bounds.get_center())
	_require(
		_frame_is_balanced(_projected_vertical_range(v9_camera, v9_bounds)),
		"V9 preview did not balance the projected full-body bounds",
	)
	_require(
		v9_full_body_distance < 3.85,
		"V9 preview retained a fixed distance instead of fitting the actor",
	)
	var v9_before_visible_frame_y := v9_camera.global_position.y
	var v9_visible_frame: Dictionary = v9_controller.handle_message(_message("frame", "v9-visible-frame", {
		"center_x": 0.0,
		"center_y": -0.12,
		"span_x": 1.64,
		"span_y": 1.64,
	}))
	_require(_is_completed(v9_visible_frame), "V9 visible-frame calibration did not complete")
	_require(
		v9_camera.global_position.y < v9_before_visible_frame_y,
		"V9 visible-frame calibration did not move a low silhouette upward in the frame",
	)
	_require(
		_is_completed(v9_controller.handle_message(_message("focus", "v9-upper", {"target": "head"})))
			and is_equal_approx(v9_camera.fov, 30.0),
		"V9 upper-body focus did not set its framing FOV",
	)
	_require(
		v9_camera.global_position.distance_to(v9_bounds.get_center()) < v9_full_body_distance,
		"V9 upper-body focus did not tighten the camera distance",
	)
	_require(
		_is_completed(v9_controller.handle_message(_message("focus", "v9-portrait", {"target": "portrait"})))
			and is_equal_approx(v9_camera.fov, 24.0),
		"V9 portrait focus did not set its framing FOV",
	)
	_require(
		_is_completed(v9_controller.handle_message(_message("reset", "v9-reset")))
			and is_equal_approx(v9_camera.fov, 36.0),
		"V9 reset did not restore the default framing FOV",
	)

	var repeated: Dictionary = controller.handle_message(_message("configure", "req-2", {
		"elfie_id": "fox-1",
		"species_id": "fox",
		"spec_revision": 7,
		"appearance": {"height_scale": 1.1},
	}))
	_require(_is_completed(repeated), "Repeated configure did not complete")
	_require(bool(repeated.get("reused_actor", false)), "Repeated configure did not report actor reuse")
	_require(characters.get_child_count() == 1, "Repeated configure rebuilt the actor")
	_require(actor.configure_calls == 1, "Repeated configure reapplied an unchanged spec revision")

	var completed_actions := [
		_message("orbit", "req-3", {"delta": {"x": 0.2, "y": -0.1}}),
		_message("pan", "req-4", {"delta": {"x": 0.1, "y": 0.08}}),
		_message("zoom", "req-5", {"delta": -0.2}),
		_message("focus", "req-6", {"target": "head"}),
		_message("preview_intent", "req-7", {"intent": {"type": "motion", "intent_id": "motion-1", "motion": "nod_head"}}),
		_message("reset", "req-8"),
		_message("capture", "req-9"),
	]
	for message: Dictionary in completed_actions:
		var response: Dictionary = controller.handle_message(message)
		_require(_is_completed(response), "%s did not complete" % message["action"])
	_require(actor.preview_intents == [{"type": "motion", "intent_id": "motion-1", "motion": "nod_head"}], "Typed preview intent was not routed to the actor")
	_require(
		controller.handle_message(
			_message("preview_intent", "req-10", {"intent": {"type": "motion", "intent_id": "motion-2", "motion": "shake_head"}}),
		).get("event") == "completed",
		"Shake-head preview should be supported",
	)
	_require(
		_is_completed(controller.handle_message(
			_message("preview_intent", "req-11", {"intent": {"type": "motion", "intent_id": "pose-1", "motion": "pose_hands_on_hips"}}),
		)),
		"Static pose preview should be supported",
	)
	_require(characters.get_child_count() == 1, "Preview controls changed the actor count")

	var rejected_messages := [
		_message("orbit", "req-2", {"delta": {"x": 0.1, "y": 0.1}}),
		_message("orbit", "bad-1", {"delta": {"x": NAN, "y": 0.0}}),
		_message("pan", "bad-2", {"delta": {"x": 10001.0, "y": 0.0}}),
		_message("zoom", "bad-3", {"delta": "near"}),
		_message("focus", "bad-4", {"target": "filesystem"}),
		_message("preview_intent", "bad-5", {"intent": {"type": "motion", "intent_id": "bad", "motion": "delete_all"}}),
		_message("frame", "bad-7", {"center_x": 0.0, "center_y": NAN, "span_x": 1.0, "span_y": 1.0}),
		_message("execute", "bad-6", {"script": "queue_free()"}),
		{"channel": "elfie-lab", "action": "reset", "request_id": ""},
	]
	for message: Dictionary in rejected_messages:
		var response: Dictionary = controller.handle_message(message)
		_require(_is_unsupported(response), "Malicious or malformed message was accepted: %s" % message)
	_require(characters.get_child_count() == 1, "Rejected messages changed the actor count")
	await _run_real_actor_contract()

	if _failed:
		quit(1)
		return
	print("PASS: Elfie Lab preview normal scenario; actor_count=1; intent=nod_head")
	print("PASS: Elfie Lab preview rejected stale, malformed, extreme, and unsupported input")
	quit(0)


func _run_real_actor_contract() -> void:
	var characters := Node3D.new()
	var camera := Camera3D.new()
	camera.set_meta(&"v9_render_profile", true)
	root.add_child(characters)
	root.add_child(camera)
	var controller := CONTROLLER_SCRIPT.new()
	root.add_child(controller)
	controller.setup(characters, camera, {"dog": DOG_SCENE})
	var response: Dictionary = controller.handle_message(_message("configure", "real-dog", {
		"elfie_id": "dog-real",
		"species_id": "dog",
		"spec_revision": 1,
		"appearance": _real_actor_appearance(),
	}))
	await process_frame
	_require(_is_completed(response), "Real dog configure did not complete")
	_require(characters.get_child_count() == 1, "Real dog actor was not created")
	var actor := characters.get_child(0) as Node3D
	var meshes := actor.find_children("*", "MeshInstance3D", true, false)
	var bounds := actor.call("visual_bounds") as AABB
	var animation_player := actor.get_node_or_null("AnimationPlayer") as AnimationPlayer
	var mesh_bounds := AABB()
	var has_mesh_bounds := false
	for node in meshes:
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var candidate_bounds := mesh_instance.global_transform * mesh_instance.get_aabb()
		if has_mesh_bounds:
			mesh_bounds = mesh_bounds.merge(candidate_bounds)
		else:
			mesh_bounds = candidate_bounds
			has_mesh_bounds = true
	_require(not bool(actor.get("install_shared_animations")), "Preview actor eagerly installed the full animation library")
	_require(bool(actor.get("install_preview_poses")), "Preview actor did not install the static pose library")
	_require(
		animation_player != null and not animation_player.playback_active,
		"Preview actor started a looping animation instead of the model rest pose",
	)
	_require(
		_frame_is_balanced(_projected_vertical_range(camera, bounds)),
		"Real dog default rest pose did not balance the projected full-body bounds: %s" % _projected_vertical_range(camera, bounds),
	)
	var pose_response: Dictionary = controller.handle_message(_message("preview_intent", "real-pose", {
		"intent": {"type": "motion", "intent_id": "pose-real", "motion": "pose_waving"},
	}))
	_require(_is_completed(pose_response), "Real dog static pose did not complete")
	await process_frame
	for pose_name in [
		"pose_hands_on_hips",
		"pose_thinking",
		"pose_thumbs_up",
		"pose_victory",
		"pose_waving",
	]:
		_require(
			animation_player != null and animation_player.has_animation(pose_name),
			"Real dog preview did not install pose animation: %s" % pose_name,
		)
	_require(
		animation_player != null and animation_player.assigned_animation == "pose_waving",
		"Real dog static pose did not select the requested animation: current=%s names=%s" % [
			animation_player.assigned_animation if animation_player != null else "<missing>",
			animation_player.get_animation_list() if animation_player != null else [],
		],
	)
	_require(
		animation_player != null and not animation_player.playback_active,
		"Real dog static pose continued playing instead of freezing",
	)
	var default_pose_response: Dictionary = controller.handle_message(_message("preview_intent", "real-default-pose", {
		"intent": {"type": "motion", "intent_id": "pose-default", "motion": "pose_default"},
	}))
	_require(_is_completed(default_pose_response), "Real dog default rest pose did not complete")
	_require(
		animation_player != null and not animation_player.playback_active,
		"Real dog default rest pose started playback",
	)
	await process_frame
	var default_bounds := actor.call("visual_bounds") as AABB
	_require(
		_frame_is_balanced(_projected_vertical_range(camera, default_bounds)),
		"Real dog default rest pose did not reframe the projected bounds: %s" % _projected_vertical_range(camera, default_bounds),
	)
	var pose_reframe_response: Dictionary = controller.handle_message(_message("preview_intent", "real-pose-reframe", {
		"intent": {"type": "motion", "intent_id": "pose-waving-reframe", "motion": "pose_waving"},
	}))
	_require(_is_completed(pose_reframe_response), "Real dog static pose did not complete during reframe verification")
	await process_frame
	var pose_bounds := actor.call("visual_bounds") as AABB
	_require(
		_frame_is_balanced(_projected_vertical_range(camera, pose_bounds)),
		"Real dog static pose did not reframe the projected bounds: %s" % _projected_vertical_range(camera, pose_bounds),
	)
	var camera_before_pose_orbit := camera.global_transform
	var pose_orbit_response: Dictionary = controller.handle_message(_message("orbit", "real-pose-orbit", {
		"delta": {"x": 0.18, "y": -0.08},
	}))
	_require(_is_completed(pose_orbit_response), "Camera orbit did not complete after a static pose was selected")
	_require(
		camera.global_transform != camera_before_pose_orbit,
		"Static pose stopped camera interaction together with the animation player",
	)
	_require(not meshes.is_empty(), "Real dog actor has no MeshInstance3D")
	_require(has_mesh_bounds, "Real dog actor has no measurable mesh bounds")
	_require(
		_appearance_uses_bind_position_attribute(meshes),
		"Real dog appearance shader did not carry bind-pose coordinates for markings",
	)
	_require(
		_has_opaque_appearance_material(meshes),
		"Real dog preview did not apply the formal opaque ActorAppearance material",
	)
	_require(not bounds.size.is_zero_approx(), "Real dog actor has empty visual bounds")
	_require(bounds.position.y <= mesh_bounds.position.y, "Real dog visual bounds omitted the mesh feet")
	_require(bounds.end.y >= mesh_bounds.end.y, "Real dog visual bounds omitted the mesh top")
	_require(camera.global_position.distance_to(bounds.get_center()) >= 1.0, "Preview camera is inside the real dog bounds")
	_require(
		camera.global_position.distance_to(bounds.get_center()) < 3.85,
		"Real dog preview camera retained the fixed V9 distance",
	)
	await _run_species_frame_contract("fox", FOX_SCENE)
	print("INFO: real dog meshes=%d bounds=%s camera=%s size=%.3f" % [
		meshes.size(),
		bounds,
		camera.global_position,
		camera.size,
	])
	controller.queue_free()
	characters.queue_free()
	camera.queue_free()


func _run_species_frame_contract(species_id: String, scene: PackedScene) -> void:
	var characters := Node3D.new()
	var camera := Camera3D.new()
	camera.set_meta(&"v9_render_profile", true)
	root.add_child(characters)
	root.add_child(camera)
	var controller := CONTROLLER_SCRIPT.new()
	root.add_child(controller)
	controller.setup(characters, camera, {species_id: scene})
	var response: Dictionary = controller.handle_message(_message("configure", "real-%s" % species_id, {
		"elfie_id": "%s-real" % species_id,
		"species_id": species_id,
		"spec_revision": 1,
		"appearance": {},
	}))
	await process_frame
	_require(_is_completed(response), "%s configure did not complete" % species_id)
	var actor := characters.get_child(0) as Node3D
	var bounds := actor.call("visual_bounds") as AABB
	var projected_range := _projected_vertical_range(camera, bounds)
	_require(
		_frame_is_balanced(projected_range),
		"%s preview camera did not balance the projected full-body bounds: %s" % [species_id, projected_range],
	)
	print("INFO: real %s bounds=%s projected_y=%s camera=%s" % [species_id, bounds, projected_range, camera.global_position])
	controller.queue_free()
	characters.queue_free()
	camera.queue_free()


func _frame_is_balanced(projected_range: Vector2) -> bool:
	var midpoint := (projected_range.x + projected_range.y) * 0.5
	return (
		projected_range.x >= -0.92
		and projected_range.y <= 0.92
		and absf(midpoint) <= 0.04
	)


func _projected_vertical_range(camera: Camera3D, bounds: AABB) -> Vector2:
	var minimum := INF
	var maximum := -INF
	for x in [bounds.position.x, bounds.end.x]:
		for y in [bounds.position.y, bounds.end.y]:
			for z in [bounds.position.z, bounds.end.z]:
				var local_point := camera.global_transform.affine_inverse() * Vector3(x, y, z)
				var depth := -local_point.z
				if depth <= 0.0:
					continue
				var value := local_point.y / (depth * tan(deg_to_rad(camera.fov * 0.5)))
				minimum = minf(minimum, value)
				maximum = maxf(maximum, value)
	return Vector2(minimum, maximum)


func _real_actor_appearance() -> Dictionary:
	return {
		"height_scale": 1.03,
		"build_scale": 0.97,
		"bone_scales": {"HeadScale": 1.04, "TailLength": 1.06},
		"material_parameters": {
			"palette_id": "silver_gray",
			"primary_color_id": "silver_gray",
			"marking_id": "heart",
			"marking_placement": "chest",
			"marking_color_id": "apricot",
			"marking_scale": 0.90,
			"marking_intensity": 0.92,
			"region_0_id": "chest_tuft",
			"region_0_color_id": "honey_gold",
			"region_0_intensity": 0.86,
			"region_1_id": "tail_underside",
			"region_1_color_id": "chocolate",
			"region_1_intensity": 0.90,
			"region_2_id": "none",
			"region_2_color_id": "silver_gray",
			"region_2_intensity": 0.0,
		},
	}


func _has_opaque_appearance_material(meshes: Array[Node]) -> bool:
	var matched := false
	for node in meshes:
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := mesh_instance.get_surface_override_material(surface_index)
			if material is ShaderMaterial:
				var shader_material := material as ShaderMaterial
				matched = (
					shader_material.shader != null
					and not shader_material.shader.code.contains("ALPHA =")
					and shader_material.get_shader_parameter("appearance_accent_region_0") == 5
					and shader_material.get_shader_parameter("appearance_accent_region_1") == 12
					and shader_material.get_shader_parameter("appearance_marking_id") == 14
					and shader_material.get_shader_parameter("appearance_marking_placement") == 5
				)
			mesh_instance.set_surface_override_material(surface_index, null)
	return matched


func _appearance_uses_bind_position_attribute(meshes: Array[Node]) -> bool:
	for node in meshes:
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null:
			continue
		if mesh_instance.mesh == null:
			continue
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var material := mesh_instance.get_surface_override_material(surface_index)
			if material is ShaderMaterial:
				var shader := (material as ShaderMaterial).shader
				var format := int(mesh_instance.mesh.surface_get_format(surface_index))
				if shader != null and shader.code.contains("CUSTOM0.xyz") and (format & Mesh.ARRAY_FORMAT_CUSTOM0) != 0:
					return true
	return false


func _create_actor(_species: String, _scene: PackedScene) -> Node3D:
	var actor := FakePreviewActor.new()
	_created_actors.append(actor)
	return actor


func _message(action: String, request_id: String, payload: Dictionary = {}) -> Dictionary:
	return {
		"channel": "elfie-lab",
		"action": action,
		"request_id": request_id,
		"payload": payload,
	}


func _is_completed(response: Dictionary) -> bool:
	return response.get("event") == "completed"


func _is_unsupported(response: Dictionary) -> bool:
	return response.get("event") == "unsupported"


func _require(condition: bool, message: String) -> void:
	if condition:
		return
	_failed = true
	push_error(message)
