extends SceneTree

const CONTROLLER_SCRIPT := preload("res://lab_preview_controller.gd")
const ACTOR_SCRIPT := preload("res://characters/shared/elfie_actor.gd")
const DOG_SCENE := preload("res://characters/dog/dog.tscn")

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
		if not ["nod_head", "shake_head"].has(String(intent.get("motion", ""))):
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
	_require(characters.get_child_count() == 1, "Preview controls changed the actor count")

	var rejected_messages := [
		_message("orbit", "req-2", {"delta": {"x": 0.1, "y": 0.1}}),
		_message("orbit", "bad-1", {"delta": {"x": NAN, "y": 0.0}}),
		_message("pan", "bad-2", {"delta": {"x": 10001.0, "y": 0.0}}),
		_message("zoom", "bad-3", {"delta": "near"}),
		_message("focus", "bad-4", {"target": "filesystem"}),
		_message("preview_intent", "bad-5", {"intent": {"type": "motion", "intent_id": "bad", "motion": "delete_all"}}),
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
	_require(not bool(actor.get("install_shared_animations")), "Preview actor eagerly installed the full animation library")
	_require(not meshes.is_empty(), "Real dog actor has no MeshInstance3D")
	_require(
		_has_opaque_appearance_material(meshes),
		"Real dog preview did not apply the formal opaque ActorAppearance material",
	)
	_require(not bounds.size.is_zero_approx(), "Real dog actor has empty visual bounds")
	_require(camera.global_position.distance_to(bounds.get_center()) >= 1.0, "Preview camera is inside the real dog bounds")
	print("INFO: real dog meshes=%d bounds=%s camera=%s size=%.3f" % [
		meshes.size(),
		bounds,
		camera.global_position,
		camera.size,
	])
	controller.queue_free()
	characters.queue_free()
	camera.queue_free()


func _real_actor_appearance() -> Dictionary:
	return {
		"height_scale": 1.03,
		"build_scale": 0.97,
		"bone_scales": {"HeadScale": 1.04, "TailLength": 1.06},
		"material_parameters": {
			"palette_id": "silver_gray",
			"primary_color_id": "silver_gray",
			"marking_id": "star",
			"marking_placement": "forehead_center",
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
					and shader_material.get_shader_parameter("appearance_marking_id") == 8
				)
			mesh_instance.set_surface_override_material(surface_index, null)
	return matched


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
