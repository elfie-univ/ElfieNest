extends Node3D

const CAMERA_REVIEW := preload("res://runtime/lab/camera_review.gd")
const GARDEN_DOOR_REVIEW := preload("res://runtime/lab/garden_door_review.gd")
const COLLISION_REVIEW := preload("res://runtime/lab/collision_review.gd")
const WATER_REVIEW := preload("res://runtime/lab/estate_water_review.gd")
const EVENT_REVIEW := preload("res://runtime/lab/estate_event_review.gd")
const PATH_LIGHTING_REVIEW := preload("res://runtime/lab/estate_path_lighting_review.gd")
const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")
const GODOT_WS_URL := "ws://127.0.0.1:8765"
const BODY_EVENT_NAMES := [
	"intent_accepted",
	"intent_started",
	"intent_terminal",
	"movement_blocked",
	"tactile_contact",
]
const WORLD_RUNTIME_CONTROLLER := preload("res://runtime/world/world_controller.gd")
const ACTOR_RUNTIME_CONTROLLER := preload("res://runtime/actor/actor_controller.gd")
const ENVIRONMENT_RUNTIME_CONTROLLER := preload("res://runtime/world/environment_controller.gd")
const OBSERVER_PRESENTATION_CONTROLLER := preload("res://runtime/observer/observer_presentation.gd")
const RUNTIME_WEBSOCKET_CLIENT := preload("res://runtime/endpoint/websocket_client.gd")
const RUNTIME_MODE := preload("res://runtime/endpoint/runtime_mode.gd")
const LAB_RUNTIME := preload("res://runtime/lab/lab_runtime.gd")
const M01_SAMPLE := preload("res://runtime/lab/m01_optical_sample.gd")
const AUTHORITY_SEMANTIC_EVENTS := preload("res://runtime/endpoint/authority_semantic_events.gd")
const AUTHORITY_ENDPOINT := preload("res://runtime/endpoint/authority_endpoint.gd")
const OBSERVER_BRIDGE := preload("res://runtime/observer/observer_bridge.gd")
const OUTDOOR_ACCESS_OVERLAY := preload("res://runtime/observer/outdoor_access_overlay.gd")
const OBSERVER_MODE_PARAMETER := "observer"
const OBSERVER_MODE_VALUE := "product"
const VISUAL_AUTHORITY_ENV := "ELFIENEST_GODOT_SHOW_VISUALS"
## Temporary monitor-only visual behavior; remove when real action control lands.
const MOCK_WANDER_ENABLED := false
const OBSERVER_LOCAL_MOCK_WANDER_ENABLED := false

@onready var nest: ModularNest = $Nest
@onready var characters: Node3D = $Characters
@onready var lab_preview: Node3D = $LabPreview
@onready var lab_camera: Camera3D = $LabPreview/Camera3D

var _ws_url := ""
var _lab_mode := false
var _nest_lab_mode := false
var _product_observer_mode := false
var _lab_runtime: Node
var _world_controller: Node
var _actor_controller: Node
var _environment_controller: Node
var _observer_presentation: Node
var _observer_bridge: Node
var _runtime_client: Node
var _runtime_mode
var _semantic_events
var _actor_scenes: Dictionary = {}
var _authority_endpoint


func add_character(
	character_scene: PackedScene,
	spawn_position: Vector3 = Vector3.ZERO,
	install_animations: bool = true,
) -> CharacterBody3D:
	var instance := character_scene.instantiate()
	if not instance is CharacterBody3D:
		instance.queue_free()
		push_error("Character scene root must be CharacterBody3D")
		return null
	var character := instance as CharacterBody3D
	if character is ElfieActor:
		(character as ElfieActor).install_shared_animations = install_animations
	characters.add_child(character)
	character.position = spawn_position
	return character


func _ready() -> void:
	if OS.has_feature("web") and _query_parameter("mode") == "navigation_tour":
		lab_preview.free()
		set_process(false)
		var tour := load("res://runtime/lab/estate_navigation_tour.gd").new() as Node
		add_child(tour)
		await tour.setup(nest, characters)
		return
	if OS.has_feature("web") and _query_parameter("mode") == "animation_journey":
		lab_preview.free()
		set_process(false)
		if preload("res://runtime/lab/estate_animation_picker_catalog.gd").uses_picker(str(JavaScriptBridge.eval("window.location.search"))):
			nest.visible=false
			var picker := load("res://runtime/lab/estate_animation_picker.gd").new() as Control
			add_child(picker)
			return
		var journey := load("res://runtime/lab/estate_animation_journey.gd").new() as Node
		add_child(journey)
		await journey.setup(nest, characters)
		return
	if OS.has_feature("web") and _query_parameter("mode") == "elfie_lab" and _query_parameter("review") in ["chair", "sofa", "tour"]:
		lab_preview.free()
		set_process(false)
		var review_path := "res://runtime/lab/sofa_world_review.gd" if _query_parameter("review") == "sofa" else "res://runtime/lab/chair_world_review.gd"
		if _query_parameter("review") == "tour": review_path = "res://runtime/lab/estate_animation_tour.gd"
		var review := load(review_path).new() as Node
		add_child(review)
		review.setup(nest, characters)
		return
	if OS.has_feature("web"):
		get_viewport().msaa_3d = Viewport.MSAA_4X
	if PATH_LIGHTING_REVIEW.is_requested():
		M01_SAMPLE.isolate_host(self)
		var review := PATH_LIGHTING_REVIEW.new()
		review.camera_owner = nest
		add_child(review)
		await _notify_web_runtime_ready()
		return
	if EVENT_REVIEW.is_requested():
		M01_SAMPLE.isolate_host(self)
		lab_preview.visible = false
		var review := EVENT_REVIEW.new()
		review.camera_owner = nest
		add_child(review)
		return
	if WATER_REVIEW.is_requested():
		M01_SAMPLE.isolate_host(self)
		lab_preview.visible = false
		var review := WATER_REVIEW.new()
		review.camera_owner = nest
		add_child(review)
		return
	if GARDEN_DOOR_REVIEW.is_requested():
		M01_SAMPLE.isolate_host(self)
		var review := GARDEN_DOOR_REVIEW.new()
		review.camera_owner = nest
		add_child(review)
		await _notify_web_runtime_ready()
		return
	if COLLISION_REVIEW.is_requested():
		enter_collision_review()
		await _notify_web_runtime_ready()
		return
	if CAMERA_REVIEW.is_requested():
		enter_camera_review()
		await _notify_web_runtime_ready()
		return
	if M01_SAMPLE.is_requested():
		M01_SAMPLE.isolate_host(self)
		var sample := M01_SAMPLE.new()
		sample.camera_owner = nest
		add_child(sample)
		return
	_actor_scenes = SPECIES_CATALOG.discover_actor_scenes()
	_lab_mode = OS.has_feature("web") and _query_parameter("mode") == "elfie_lab"
	_nest_lab_mode = OS.has_feature("web") and _query_parameter("lab") == "nest_lab"
	_product_observer_mode = (
		OS.has_feature("web")
		and _query_parameter(OBSERVER_MODE_PARAMETER) == OBSERVER_MODE_VALUE
	)
	_setup_lab_runtime()
	if _lab_mode:
		_lab_runtime.setup_elfie_lab()
		return
	if _nest_lab_mode:
		_lab_runtime.setup_nest_lab()
		nest.set_observation_hud_visible(true)
	if _product_observer_mode:
		_enter_product_observer_presentation_mode()
		_setup_observer_presentation()
		var access_overlay := OUTDOOR_ACCESS_OVERLAY.new()
		add_child(access_overlay)
		await access_overlay.setup(nest)
		nest.add_lighting_observer_views()
		nest.show_observation_hud = false
		nest.set_observation_hud_visible(false)
		_setup_product_observer_bridge()
		await _notify_web_runtime_ready()
		_observer_bridge.publish_catalog()
		return
	_runtime_mode = RUNTIME_MODE.new()
	_runtime_mode.setup(_resolve_runtime_mode())
	if (
		_runtime_mode.disables_visual_runtime_services()
		and not _show_visual_authority()
		and not _nest_lab_mode
	):
		nest.physical_authority = true
		nest.visible = false
	if not _runtime_mode.allows_authority_transport():
		if _runtime_mode.requires_web_ready_signal():
			await _notify_web_runtime_ready()
		return
	_start_authority_runtime()


func _show_visual_authority() -> bool:
	var value := OS.get_environment(VISUAL_AUTHORITY_ENV).strip_edges().to_lower()
	return value in ["1", "true", "yes"]


func _process(_delta: float) -> void:
	if _lab_mode:
		_lab_runtime.process_elfie_lab_frame()
		return
	if _nest_lab_mode:
		_lab_runtime.process_nest_lab_frame()
		if _runtime_client != null:
			_runtime_client.process_frame()
		return
	if _product_observer_mode:
		_observer_bridge.process_frame()
		return
	if _runtime_client != null:
		_runtime_client.process_frame()


func _setup_lab_runtime() -> void:
	_lab_runtime = LAB_RUNTIME.new()
	add_child(_lab_runtime)
	_lab_runtime.setup(nest, characters, lab_preview, lab_camera, _actor_scenes)


func _start_authority_runtime() -> void:
	_semantic_events = AUTHORITY_SEMANTIC_EVENTS.new()
	_authority_endpoint = AUTHORITY_ENDPOINT.new()
	_world_controller = WORLD_RUNTIME_CONTROLLER.new()
	add_child(_world_controller)
	_world_controller.setup(nest)
	_world_controller.runtime_event.connect(_on_runtime_event)
	_actor_controller = ACTOR_RUNTIME_CONTROLLER.new()
	add_child(_actor_controller)
	_actor_controller.setup(
		nest,
		characters,
		_actor_scenes,
		true,
		MOCK_WANDER_ENABLED,
	)
	_world_controller.set_actor_provider(_actor_controller.actor_instances)
	_actor_controller.runtime_event.connect(_on_runtime_event)
	_environment_controller = ENVIRONMENT_RUNTIME_CONTROLLER.new()
	add_child(_environment_controller)
	_environment_controller.setup(nest)
	_environment_controller.runtime_event.connect(_on_runtime_event)
	_ws_url = _resolve_runtime_ws_url()
	_runtime_client = RUNTIME_WEBSOCKET_CLIENT.new()
	add_child(_runtime_client)
	_runtime_client.command_message.connect(_handle_runtime_command)
	_runtime_client.setup(_ws_url, _resolve_handshake_nonce())


func _setup_observer_presentation() -> void:
	_observer_presentation = OBSERVER_PRESENTATION_CONTROLLER.new()
	add_child(_observer_presentation)
	_observer_presentation.setup(
		nest,
		characters,
		_actor_scenes,
		OBSERVER_LOCAL_MOCK_WANDER_ENABLED,
	)
	_observer_bridge = OBSERVER_BRIDGE.new()
	add_child(_observer_bridge)
	_observer_bridge.setup(nest, _observer_presentation, _product_observer_mode)


func _handle_runtime_command(message: Dictionary) -> void:
	var command_name := String(message.get("name", ""))
	var payload: Variant = message.get("payload", {})
	if not payload is Dictionary or not _authority_endpoint.validate_command(
		message,
		command_name,
		payload as Dictionary,
		String(_runtime_client.runtime_id),
		int(_runtime_client.runtime_generation),
		nest.world_revision,
	):
		return
	match command_name:
		"configure_world":
			await _world_controller.configure_world(
				payload as Dictionary,
				String(message.get("message_id", "")),
			)
		"sync_actors":
			var result: Dictionary = _actor_controller.sync_actors(
				(payload as Dictionary).get("actors", []),
			)
			if bool(result.get("accepted", false)):
				_send_runtime_event(
					"world_snapshot",
					result.get("snapshot", {}) as Dictionary,
					String(message.get("message_id", "")),
				)
			else:
				_send_runtime_event(
					"startup_error",
					result,
					String(message.get("message_id", "")),
				)
		"request_speech_reach":
			_world_controller.resolve_speech_reach(payload as Dictionary)
		"request_visual_observation":
			_world_controller.resolve_visual_observation(payload as Dictionary)
		"apply_environment":
			_environment_controller.apply_environment(payload as Dictionary)
		"execute_intent":
			_actor_controller.execute_intent(payload as Dictionary)
		"cancel_intent":
			_actor_controller.cancel_intent(payload as Dictionary)
		_:
			return


func _on_runtime_event(
	event_name: String,
	payload: Dictionary,
	cause_id: String,
) -> void:
	var semantic_event: Dictionary = _semantic_events.project(
		event_name,
		payload,
		cause_id,
	)
	_send_runtime_event(
		String(semantic_event["name"]),
		semantic_event["payload"] as Dictionary,
		String(semantic_event.get("cause_id", "")),
	)


func _resolve_handshake_nonce() -> String:
	var environment_nonce := OS.get_environment("ELFIENEST_GODOT_NONCE")
	if not environment_nonce.is_empty():
		return environment_nonce
	if not OS.has_feature("web"):
		return ""
	return _query_parameter("nonce")


func _resolve_runtime_mode() -> String:
	var environment_mode := OS.get_environment("ELFIENEST_GODOT_MODE")
	if not environment_mode.is_empty():
		return environment_mode
	if OS.has_feature("dedicated_server") or DisplayServer.get_name() == "headless":
		return "authority"
	if OS.has_feature("web"):
		return _query_parameter("mode")
	return "authority"


func _resolve_runtime_ws_url() -> String:
	var environment_url := OS.get_environment("ELFIENEST_GODOT_WS")
	if not environment_url.is_empty():
		return environment_url
	if OS.has_feature("web"):
		var query_url := _query_parameter("ws")
		if _is_loopback_websocket_url(query_url):
			return query_url
	return GODOT_WS_URL


func _is_loopback_websocket_url(value: String) -> bool:
	var normalized := value.strip_edges()
	if not normalized.begins_with("ws://") or normalized.find("@") != -1:
		return false
	var authority := normalized.trim_prefix("ws://")
	if authority.contains("/") or authority.contains("?") or authority.contains("#"):
		return false
	var separator := authority.rfind(":")
	if separator <= 0:
		return false
	var hostname := authority.left(separator).to_lower()
	var port := authority.substr(separator + 1)
	if hostname not in ["127.0.0.1", "localhost"] or not port.is_valid_int():
		return false
	var port_number := int(port)
	return port_number >= 1 and port_number <= 65535


func _setup_product_observer_bridge() -> void:
	_observer_bridge.setup_web_bridge()


func _enter_product_observer_presentation_mode() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


func _query_parameter(name: String) -> String:
	var query: Variant = JavaScriptBridge.eval("window.location.search")
	if not query is String:
		return ""
	for part in String(query).trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2 and pair[0] == name:
			return String(pair[1]).uri_decode()
	return ""


func _send_runtime_event(event_name: String, payload: Dictionary, cause_id: String = "") -> void:
	var body_event := event_name in BODY_EVENT_NAMES
	_runtime_client.send_runtime_event(
		event_name,
		payload,
		nest.world_revision,
		"body" if body_event else "nest",
		String(payload.get("actor_id", "")) if body_event else "",
		cause_id,
	)


func _notify_web_runtime_ready() -> void:
	"""Emit the existing iframe readiness contract for observer-only Web modes."""
	if not OS.has_feature("web"):
		return
	for _frame in range(4):
		await get_tree().process_frame
	JavaScriptBridge.eval(
		"window.__elfieNestObserverReady = true;"
		+ "window.parent.postMessage('elfienest:godot-web-ready', window.location.origin)"
	)


func enter_collision_review() -> void:
	# Explicit visual review only: return before catalog/authority setup.
	M01_SAMPLE.isolate_host(self)
	var review := COLLISION_REVIEW.new()
	review.name = "CollisionReview"
	review.camera_owner = nest
	add_child(review)


func enter_camera_review() -> void:
	M01_SAMPLE.isolate_host(self)
	var review := CAMERA_REVIEW.new()
	review.name = "CameraReview"
	review.camera_owner = nest
	add_child(review)
