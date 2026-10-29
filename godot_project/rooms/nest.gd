@tool
class_name ModularNest
extends Node3D

signal observer_camera_catalog_changed(catalog: Dictionary)

const GARDEN_DOOR_REVIEW := preload("res://runtime/lab/garden_door_review.gd")
const COLLISION_REVIEW := preload("res://runtime/lab/collision_review.gd")
const WATER_REVIEW := preload("res://runtime/lab/estate_water_review.gd")
const EVENT_REVIEW := preload("res://runtime/lab/estate_event_review.gd")
const ESTATE_LIGHTING := preload("res://rooms/estate/estate_lighting.gd")
const PATH_LIGHTING_REVIEW := preload("res://runtime/lab/estate_path_lighting_review.gd")
const CHAIR_REVIEW_REQUEST := preload("res://runtime/lab/chair_review_request.gd")
const COMPLETE_SCENE_PATH := "res://rooms/estate/estate.tscn"
const ESTATE_PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const ESTATE_SEMANTICS := preload("res://rooms/estate/estate_semantics.gd")
const COLLISION_LAYERS := preload("res://runtime/world/collision_layers.gd")
const M01_SAMPLE := preload("res://runtime/lab/m01_optical_sample.gd")
const FIXED_BED_COUNT: int = 32
const CAMERA_ORBIT_SPEED: float = 0.008
const FOLLOW_CAMERA_OFFSET := Vector3(1.8, 1.0, 2.2)
const CAMERA_MIN_PITCH: float = deg_to_rad(12.0)
const CAMERA_MAX_PITCH: float = deg_to_rad(82.0)
const CAMERA_MIN_SIZE: float = 5.0
const CAMERA_MAX_SIZE: float = 500.0
const TOP_DOWN_MIN_HEIGHT: float = 18.0
const ENVIRONMENT_OBJECT_ID := "nest/environment"
# Front oblique composition focuses on the building, front cabins and plaza.
# Keep the orbit target low so zooming out does not fill the frame with sky.
const REFERENCE_REVIEW_POSITION := Vector3(16, 16, 46)
const REFERENCE_REVIEW_TARGET := Vector3(0, 3, 7)

var bed_count: int = FIXED_BED_COUNT:
	set(_value):
		bed_count = FIXED_BED_COUNT

@export var show_observation_hud: bool = true

@export var regenerate_editor_preview: bool = false:
	set(value):
		regenerate_editor_preview = false
		if value and Engine.is_editor_hint() and is_inside_tree():
			call_deferred("rebuild")

var _rebuilding := false
var _camera_target := Vector3.ZERO
var _camera_default_target := Vector3.ZERO
var _camera_yaw: float = 0.0
var _camera_pitch: float = 0.0
var _camera_distance: float = TOP_DOWN_MIN_HEIGHT
var _camera_default_distance: float = TOP_DOWN_MIN_HEIGHT
var _camera_default_size: float = 22.0
var _camera_views: Array[Dictionary] = []
var _active_camera_index: int = 0
var _active_camera_id := "overview"
var _observer_presentation_paused := false
var camera_catalog_revision: int = 0
var world_revision: int = 0
var _nest_id := "local-nest"
var _lights_on := true
var _observer_water: Node3D
var _observer_optics: RefCounted
var _observer_environment: Dictionary = {}
var _observer_lighting_preview := "live"
var _lighting_preview_available := false
var _observer_occupied_zones := PackedStringArray()
var _quiet_mode := false
var _lighting_usage_seconds := 0.0
var _lighting_occupied_zones := PackedStringArray()

func _refresh_usage_lighting(delta: float) -> void:
	if Engine.is_editor_hint() or _estate_lighting==null or not _observer_environment.is_empty(): return
	_lighting_usage_seconds+=delta
	if _lighting_usage_seconds<0.5: return
	_lighting_usage_seconds=0.0
	var occupied := _runtime_occupied_zones()
	if occupied==_lighting_occupied_zones: return
	_lighting_occupied_zones=occupied
	_estate_lighting.apply(_lights_on,_quiet_mode,occupied,true)
var _anchor_markers: Dictionary = {}
var _facility_markers: Dictionary = {}
var _estate_physics: Node3D
var _estate_semantics: RefCounted
var _estate_lighting: RefCounted
var _navigation_region: NavigationRegion3D

@onready var _observation_hud: CanvasLayer = $ObservationHUD


func _ready() -> void:
	if OS.has_feature("web") and preload("res://runtime/lab/estate_animation_picker_catalog.gd").uses_picker(str(JavaScriptBridge.eval("window.location.search"))):
		_observation_hud.visible=false
		return
	if not Engine.is_editor_hint() and CHAIR_REVIEW_REQUEST.is_requested():
		_observation_hud.visible = false
		return
	if not Engine.is_editor_hint() and (
		PATH_LIGHTING_REVIEW.is_requested() or COLLISION_REVIEW.is_requested()
		or GARDEN_DOOR_REVIEW.is_requested() or M01_SAMPLE.is_requested("camera_review")
	):
		_observation_hud.visible = true
		return
	if not Engine.is_editor_hint() and (
		M01_SAMPLE.is_requested() or WATER_REVIEW.is_requested() or EVENT_REVIEW.is_requested()
	):
		_observation_hud.visible = false
		return
	if Engine.is_editor_hint():
		_observation_hud.visible = false
		rebuild()
	else:
		_observation_hud.visible = show_observation_hud
		_observation_hud.connect("view_selected", select_observation_view)
		call_deferred("rebuild")


func configure_m01_optical_sample(camera: Camera3D, target: Vector3) -> void:
	# Reuse the existing orbit/pan/reset implementation without building a world.
	_camera_views.clear()
	_register_observation_view("m01-sample", "M01 optical sample", camera, target)
	select_observation_view(0)


func configure_camera_review(camera: Camera3D, target: Vector3, labels: PackedStringArray) -> void:
	# Only the explicit local review installs these presets in the existing HUD.
	_camera_views.clear()
	var ids := ["overview", "camera-review-left", "camera-review-right", "camera-review-reset"]
	for index in range(ids.size()):
		_register_observation_view(ids[index], labels[index], camera, target)
	_observation_hud.call("set_views", labels, 0)
	if not _observation_hud.is_connected("view_selected", select_observation_view):
		_observation_hud.connect("view_selected", select_observation_view)
	_observation_hud.visible = true
	select_observation_view(0)


func _unhandled_input(event: InputEvent) -> void:
	if Engine.is_editor_hint():
		return
	if _observer_presentation_paused:
		return
	var camera := _active_camera()
	if camera == null:
		return
	if event is InputEventMouseMotion:
		var mouse_motion := event as InputEventMouseMotion
		if mouse_motion.button_mask & MOUSE_BUTTON_MASK_LEFT:
			_camera_yaw = wrapf(
				_camera_yaw - mouse_motion.relative.x * CAMERA_ORBIT_SPEED,
				-PI,
				PI
			)
			_camera_pitch = clampf(
				_camera_pitch - mouse_motion.relative.y * CAMERA_ORBIT_SPEED,
				deg_to_rad(-35) if _camera_views[_active_camera_index].has("floor_height_limits") else CAMERA_MIN_PITCH,
				CAMERA_MAX_PITCH
			)
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
		elif mouse_motion.button_mask & MOUSE_BUTTON_MASK_RIGHT:
			var viewport_height := maxf(get_viewport().get_visible_rect().size.y, 1.0)
			var visible_height := camera.size
			if camera.projection == Camera3D.PROJECTION_PERSPECTIVE:
				visible_height = (
					2.0
					* _camera_distance
					* tan(deg_to_rad(camera.fov / 2.0))
				)
			var pan_scale := visible_height / viewport_height
			var camera_basis := camera.global_transform.basis
			_camera_target += (
				-camera_basis.x * mouse_motion.relative.x
				+ camera_basis.y * mouse_motion.relative.y
			) * pan_scale
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton:
		var mouse_button := event as InputEventMouseButton
		if not mouse_button.pressed:
			return
		if mouse_button.button_index == MOUSE_BUTTON_WHEEL_UP:
			if camera.projection == Camera3D.PROJECTION_PERSPECTIVE:
				camera.fov = clampf(camera.fov * 0.9, 30.0, 100.0)
			else:
				camera.size = clampf(camera.size * 0.9, CAMERA_MIN_SIZE, CAMERA_MAX_SIZE)
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
		elif mouse_button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			if camera.projection == Camera3D.PROJECTION_PERSPECTIVE:
				camera.fov = clampf(camera.fov / 0.9, 30.0, 100.0)
			else:
				camera.size = clampf(camera.size / 0.9, CAMERA_MIN_SIZE, CAMERA_MAX_SIZE)
			_apply_camera_transform(camera)
			get_viewport().set_input_as_handled()
	elif event is InputEventKey:
		var key_event := event as InputEventKey
		if key_event.pressed and not key_event.echo:
			if key_event.keycode in [KEY_R, KEY_HOME]:
				_reset_camera()
				get_viewport().set_input_as_handled()
			elif key_event.keycode == KEY_0:
				select_observation_view(0)
				get_viewport().set_input_as_handled()
			elif key_event.keycode == KEY_PAGEUP:
				_cycle_observation_view(-1)
				get_viewport().set_input_as_handled()
			elif key_event.keycode == KEY_PAGEDOWN:
				_cycle_observation_view(1)
				get_viewport().set_input_as_handled()


func rebuild() -> void:
	if _rebuilding:
		return
	_rebuilding = true
	if _observer_optics != null:
		_observer_optics.apply_environment(1.0, true)
	_observer_water = null
	_observer_optics = null
	if is_instance_valid(_navigation_region):
		remove_child(_navigation_region)
		_navigation_region.free()
	_navigation_region = null
	var previous := get_node_or_null("Generated")
	if previous != null:
		remove_child(previous)
		previous.free()
	_anchor_markers.clear()
	_facility_markers.clear()
	_camera_views.clear()
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)
	var estate := (load(COMPLETE_SCENE_PATH) as PackedScene).instantiate() as Node3D
	estate.name = "CompleteEstate"
	generated.add_child(estate)
	_estate_physics = ESTATE_PHYSICS.new()
	_estate_physics.name = "EstatePhysics"
	generated.add_child(_estate_physics)
	if not Engine.is_editor_hint():
		_estate_physics.build(estate)
	_estate_semantics = ESTATE_SEMANTICS.new()
	_estate_semantics.build(generated, estate)
	if _estate_physics.outdoor_access != null:
		_estate_semantics.restrict_outdoor_anchors(_estate_physics.outdoor_access)
	_anchor_markers = _estate_semantics.anchors
	_facility_markers = _estate_semantics.facilities
	var restore_lighting_preview := _lighting_preview_available
	_lighting_preview_available = false
	_build_observation_views(generated, estate)
	if restore_lighting_preview:
		add_lighting_observer_views()
	_observer_water = null
	_observer_optics = null
	_estate_lighting = ESTATE_LIGHTING.new()
	_estate_lighting.bind(self)
	_estate_lighting.apply(_lights_on,_quiet_mode,_runtime_occupied_zones(),true)
	_rebuilding = false
	if not _observer_environment.is_empty(): _apply_observer_lighting_display()


func apply_world_config(config: Dictionary) -> Dictionary:
	var requested_nest_id := String(config.get("nest_id", ""))
	var raw_bed_count: Variant = config.get("bed_count")
	var raw_revision: Variant = config.get("world_revision")
	if requested_nest_id.is_empty():
		return _config_rejected("invalid_nest_id")
	var requested_bed_count := _parse_protocol_integer(raw_bed_count)
	if requested_bed_count != FIXED_BED_COUNT:
		return _config_rejected("invalid_bed_count")
	var requested_revision := _parse_protocol_integer(raw_revision)
	if requested_revision < 0:
		return _config_rejected("invalid_revision")
	if requested_revision < world_revision:
		return _config_rejected("stale_revision")
	if requested_revision == world_revision:
		if requested_nest_id == _nest_id and requested_bed_count == bed_count:
			return {"accepted": true, "manifest": scene_manifest()}
		return _config_rejected("revision_conflict")

	_nest_id = requested_nest_id
	world_revision = requested_revision
	bed_count = requested_bed_count
	return {"accepted": true, "manifest": scene_manifest()}


func apply_observer_world_config(config: Dictionary) -> bool:
	var requested_nest_id := String(config.get("nest_id", ""))
	var requested_bed_count := _parse_protocol_integer(config.get("bed_count"))
	if requested_nest_id.is_empty() or requested_nest_id != _nest_id:
		return false
	if requested_bed_count != FIXED_BED_COUNT:
		return false
	if requested_bed_count == bed_count:
		return true
	bed_count = requested_bed_count
	return true


func _parse_protocol_integer(value: Variant) -> int:
	if value is int:
		return int(value)
	if value is float:
		var float_value := float(value)
		if is_nan(float_value) or is_inf(float_value):
			return -1
		var integer_value := int(float_value)
		if float(integer_value) == float_value:
			return integer_value
	return -1


func resolve_anchor(anchor_id: String) -> Marker3D:
	var marker := _anchor_markers.get(anchor_id) as Marker3D
	return null if marker != null and bool(marker.get_meta("access_restricted",false)) else marker


func resolve_facility(facility_id: String) -> Marker3D:
	return _facility_markers.get(facility_id) as Marker3D


func semantic_anchor_ids() -> Array[String]:
	var ids: Array[String] = []
	for anchor_id: Variant in _anchor_markers.keys():
		if resolve_anchor(String(anchor_id)) != null:
			ids.append(String(anchor_id))
	ids.sort()
	return ids


func apply_environment_state(
	object_id: String,
	lights_on: bool,
	quiet_mode: bool,
) -> Dictionary:
	if object_id != ENVIRONMENT_OBJECT_ID:
		return {
			"object_id": object_id,
			"lights_on": lights_on,
			"quiet_mode": quiet_mode,
			"applied": false,
			"reason": "unsupported_environment_object",
		}
	var generated := get_node_or_null("Generated")
	if generated == null or _estate_lighting == null:
		return {
			"object_id": object_id,
			"lights_on": lights_on,
			"quiet_mode": quiet_mode,
			"applied": false,
			"reason": "world_not_built",
		}
	_lights_on = lights_on
	_quiet_mode = quiet_mode
	_estate_lighting.apply(lights_on,quiet_mode,_runtime_occupied_zones(),true)
	return {
		"object_id": object_id,
		"lights_on": lights_on,
		"quiet_mode": quiet_mode,
		"applied": true,
	}


func apply_observer_environment(environment: Dictionary, entities: Dictionary = {}) -> void:
	_observer_environment = environment.duplicate()
	_observer_occupied_zones=ESTATE_LIGHTING.occupied_zones(entities)
	_apply_observer_lighting_display()


func _runtime_occupied_zones() -> PackedStringArray:
	var entities: Dictionary = {}
	if _estate_semantics==null: return PackedStringArray()
	for actor: Node in get_tree().get_nodes_in_group(&"runtime_elfie_actors"):
		if actor is ElfieActor and (actor as ElfieActor).is_visible_in_tree():
			entities[(actor as ElfieActor).elfie_id]={"active":true,"posture":(actor as ElfieActor).runtime_posture(),"zone_id":_estate_semantics.nearest_zone((actor as ElfieActor).global_position)}
	return ESTATE_LIGHTING.occupied_zones(entities)


func _apply_observer_lighting_display() -> void:
	if get_node_or_null("Generated/CompleteEstate") == null: return
	if _observer_optics == null:
		_observer_optics = preload("res://rooms/estate/estate_lighting_sample.gd").new()
		_observer_optics.bind_m01(self)
	var preview := _observer_lighting_preview != "live"
	if _observer_environment.is_empty() and not preview: return
	var phase := str(_observer_environment.get("phase", "day"))
	var enabled := bool(_observer_environment.get("lights_on", false))
	var quiet := bool(_observer_environment.get("quiet_mode", false))
	if preview:
		phase = "night" if _observer_lighting_preview in ["night", "quiet"] else "day"
		enabled = phase == "night"
		quiet = _observer_lighting_preview == "quiet"
	var daylight := {"day": 1.0, "dawn": 1.0, "dusk": 0.0, "night": 0.0}
	_observer_optics.apply_environment(float(daylight.get(phase, 1.0)), enabled,true,quiet,_observer_occupied_zones,not preview)
	if _observer_water == null:
		_observer_water = preload("res://rooms/estate/estate_water_display.gd").new()
		_observer_water.name = "ObserverFountainLighting"
		get_node("Generated").add_child(_observer_water)
		_observer_water.bind(get_node("Generated/CompleteEstate"), $WorldEnvironment.environment, false)
		_observer_water.set_process(not _observer_presentation_paused)
	_observer_water.set_night(phase in ["dusk","night"] and not quiet)


func add_lighting_observer_views() -> void:
	if _lighting_preview_available: return
	_lighting_preview_available = true
	var parent := get_node("Generated") as Node3D
	_add_complete_view(parent, "estate-ring", "环形路", to_global(Vector3(-20, 3.4, -8)), to_global(Vector3(-12, 0.8, -13)))
	_active_camera_index = _observation_view_index_by_id(_active_camera_id)
	camera_catalog_revision += 1
	_emit_observer_camera_catalog_changed()


func nearest_zone_id(world_position: Vector3) -> String:
	return _estate_semantics.nearest_zone(world_position) if _estate_semantics != null else ""


func _config_rejected(code: String) -> Dictionary:
	return {
		"accepted": false,
		"code": code,
		"world_revision": world_revision,
	}


func _build_observation_views(generated: Node3D, estate: Node3D) -> void:
	var previous_id := _active_camera_id
	var room_floors: Dictionary = {}
	var room_floor_tops: Dictionary = {}
	var terrace_floors: Dictionary = {}
	var central_floor_tops: Dictionary = {}
	var central_floor_bottoms: Dictionary = {}
	var arrival_platform_center := Vector3.ZERO
	var arrival_steps_center := Vector3.ZERO
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		var module_name := str(extras.get("module", ""))
		var source := str(extras.get("source_name", mesh.name))
		if module_name == "central" and source == "Roof01 complete raised landing platform":
			arrival_platform_center = ((global_transform.affine_inverse() * mesh.global_transform) * mesh.get_aabb()).get_center()
		if module_name == "central" and str(extras.get("assembly", "")) == "roof01_steps":
			arrival_steps_center = ((global_transform.affine_inverse() * mesh.global_transform) * mesh.get_aabb()).get_center()
		if source.contains("continuous lower floor"):
			room_floors[module_name] = mesh.global_transform
			room_floor_tops[module_name] = mesh.get_aabb().end.y
		if source == "ROOM • inset terrace walking finish":
			terrace_floors[module_name] = mesh
		if module_name == "central" and source in [
			"Central L1 fitted complete floor",
			"Central L2 complete slab with stair opening",
			"Central L3 complete slab with stair opening",
		]:
			var local_bounds := (global_transform.affine_inverse() * mesh.global_transform) * mesh.get_aabb()
			central_floor_tops[int(extras["floor"])] = local_bounds.end.y
			central_floor_bottoms[int(extras["floor"])] = local_bounds.position.y
		if module_name == "central" and source.begins_with("Central L4 round arrival floor"):
			central_floor_tops[4] = _arrival_floor_top(mesh)
			central_floor_bottoms[4] = ((global_transform.affine_inverse()*mesh.global_transform)*mesh.get_aabb()).position.y
	# Keep the internal overview action/fallback while presenting only one outdoor view.
	var overview := get_node("Camera3D") as Camera3D
	overview.projection = Camera3D.PROJECTION_PERSPECTIVE
	overview.fov = 38.0
	overview.near = 0.05
	overview.far = 1000.0
	overview.global_position = to_global(REFERENCE_REVIEW_POSITION)
	overview.look_at(to_global(REFERENCE_REVIEW_TARGET))
	_register_observation_view("overview", "庭院与建筑", overview, to_global(REFERENCE_REVIEW_TARGET))
	for floor_number in range(1, 5):
		var floor_y := float(central_floor_tops[floor_number])
		var camera_position := Vector3(0, floor_y + 1.4, 5.2)
		var target := Vector3(0, floor_y + 0.8, 0)
		var field_of_view := 70.0
		if floor_number == 1:
			# Wall-side gap between the front and side doorways, clear of chairs.
			camera_position = Vector3(6.2, floor_y + 2.1, 4.5)
			target = Vector3(0, floor_y + 0.95, -0.2)
			field_of_view = 80.0
		elif floor_number in [2, 3]:
			# The empty wall-side corner clears the front chairs and the desk.
			camera_position = Vector3(6.2, floor_y + 2.3, 4.5)
			target = Vector3(0, floor_y + 0.85, 0.4)
			field_of_view = 80.0
			if floor_number == 3:
				# Look between the reading armchairs rather than over their backs.
				camera_position = Vector3(7.5, floor_y + 2.3, 2.1)
				target = Vector3(0.2, floor_y + 0.85, 1.1)
		elif floor_number == 4:
			# Face the small platform steps, along the arriving actor's walk-down axis.
			var outward := arrival_steps_center - arrival_platform_center
			outward.y = 0
			camera_position = arrival_platform_center + outward.normalized() * 5.0
			camera_position.y = floor_y + 1.8
			target = Vector3(arrival_platform_center.x, floor_y + 1.0, arrival_platform_center.z)
			field_of_view = 80.0
		_add_complete_view(generated, "central-%d" % floor_number, "主楼 · %d 层" % floor_number, to_global(camera_position), to_global(target), field_of_view)
		_camera_views.back()["floor_height_limits"] = Vector2(to_global(Vector3(0,floor_y+0.25,0)).y, to_global(Vector3(0,float(central_floor_bottoms[floor_number+1])-0.25,0)).y if central_floor_bottoms.has(floor_number+1) else INF)
	for index in range(1, 9):
		var module_name := "M%02d" % index
		if not room_floors.has(module_name):
			continue
		var floor_frame: Transform3D = room_floors[module_name]
		# Approved face-level framing in each module's own rotated source frame.
		var walking_y := float(room_floor_tops[module_name])
		var lower_position := Vector3(0,walking_y+1.8,-2.65)
		var lower_target := Vector3(-0.12,walking_y+0.95,-0.3)
		_add_complete_view(generated, "dorm-%02d" % index, "宿舍 %s · 一层" % module_name, floor_frame * lower_position, floor_frame * lower_target, 100.0)
		if terrace_floors.has(module_name):
			var terrace := terrace_floors[module_name] as MeshInstance3D
			var surface := terrace.get_aabb()
			var center := surface.get_center()
			# Inset from the curved edge: the AABB corner itself is outside the floor.
			var camera_position := Vector3(surface.position.x+1.15,surface.end.y+1.85,surface.position.z+1.65)
			var target := Vector3(center.x,surface.end.y+1.0,center.z+0.8)
			_add_complete_view(generated, "terrace-%02d" % index, "宿舍 %s · 二层露台" % module_name, terrace.global_transform * camera_position, terrace.global_transform * target,85.0)
			(_camera_views.back()["camera"] as Camera3D).keep_aspect = Camera3D.KEEP_WIDTH
	# Explicit local inspection uses the same complete world and monitor controls.
	if OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(parent.location.search).get('stair_review')")) == "1":
		_add_stair_joint_views(generated,central_floor_tops)
	var labels := observation_view_labels()
	camera_catalog_revision += 1
	_active_camera_index = _observation_view_index_by_id(previous_id)
	if _active_camera_index < 0:
		_active_camera_index = _observation_view_index_by_id("overview")
	if _active_camera_index < 0:
		_active_camera_index = 0
	if not Engine.is_editor_hint() and _observation_hud != null:
		_observation_hud.call("set_views", labels, _active_camera_index)
	select_observation_view(_active_camera_index)
	_emit_observer_camera_catalog_changed()


func _add_stair_joint_views(generated: Node3D, floors: Dictionary) -> void:
	for floor_number in [2,3,4]:
		var floor_y := float(floors[floor_number])
		var angle := deg_to_rad(-153.0 if floor_number==2 else -115.0)
		var radial := Vector3(cos(angle),0,sin(angle))
		var tangent := Vector3(-sin(angle),0,cos(angle))
		for side in [0,1]:
			var radius := 3.18 if side==0 else 4.65
			var outward := -radial if side==0 else radial
			for part in [0,1,2]:
				var height := 0.45 if part==0 else (0.90 if part==1 else 0.06)
				var target := radial*radius+Vector3.UP*(floor_y+height)
				var position := target+outward*(1.25 if part==0 else 0.65)-tangent*0.65
				position.y+=0.08
				_add_complete_view(generated,"stair-joint-%d-%d-%d" % [floor_number,side,part],"接头检查 · %d层 · %s · %s" % [floor_number,"内侧" if side==0 else "外侧",["整体","扶手封头","底部"][part]],to_global(position),to_global(target),70.0)


func _arrival_floor_top(mesh: MeshInstance3D) -> float:
	# The source includes a raised surround: its full AABB top is not the floor.
	# Intersect the actual triangles at the central axis to find the walking plane.
	var frame := global_transform.affine_inverse() * mesh.global_transform
	var faces := mesh.mesh.get_faces()
	var top: float = -INF
	for index in range(0, faces.size(), 3):
		var a: Vector3 = frame * faces[index]
		var b: Vector3 = frame * faces[index + 1]
		var c: Vector3 = frame * faces[index + 2]
		var denominator := (b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z)
		if absf(denominator) < 0.000001:
			continue
		var u := ((b.z - c.z) * -c.x + (c.x - b.x) * -c.z) / denominator
		var v := ((c.z - a.z) * -c.x + (a.x - c.x) * -c.z) / denominator
		var w := 1.0 - u - v
		if minf(u, minf(v, w)) >= -0.000001:
			top = maxf(top, u * a.y + v * b.y + w * c.y)
	assert(is_finite(top), "Arrival source has no central walking surface")
	return top


func _add_complete_view(parent: Node3D, view_id: String, label: String, position: Vector3, target: Vector3, fov: float = 70.0) -> void:
	var camera := Camera3D.new()
	camera.name = view_id
	camera.fov = fov
	camera.near = 0.05
	camera.far = 1000.0
	parent.add_child(camera)
	camera.global_position = position
	camera.look_at(target)
	_register_observation_view(view_id, label, camera, target)


func _register_observation_view(
	view_id: String,
	label: String,
	camera: Camera3D,
	target: Vector3
) -> void:
	_camera_views.append({
		"id": view_id,
		"label": label,
		"camera": camera,
		"target": target,
		"transform": camera.global_transform,
		"size": camera.size,
		"fov": camera.fov,
	})


func add_access_observer_views() -> void:
	if _observation_view_index_by_id("access-estate") >= 0: return
	var parent := get_node("Generated") as Node3D
	for spec: Array in [
		["access-estate","室外碰撞与活动范围",Vector3(10,72,42),Vector3(0,0,-2),108.0],
		["access-forest","森林小路边界",Vector3(-3,46,-16),Vector3(-3,0,-24),70.0],
	]:
		_add_complete_view(parent,spec[0],spec[1],to_global(spec[2]),to_global(spec[3]))
		var view: Dictionary = _camera_views.pop_back()
		var camera := view["camera"] as Camera3D
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.keep_aspect = Camera3D.KEEP_WIDTH
		camera.size = spec[4]
		view["size"] = camera.size
		_camera_views.insert(1 if spec[0] == "access-estate" else 2,view)
	_active_camera_index = _observation_view_index_by_id(_active_camera_id)
	camera_catalog_revision += 1
	_emit_observer_camera_catalog_changed()


func observation_view_count() -> int:
	return _camera_views.size()


func register_observer_actor_camera(actor_id: String, actor: CharacterBody3D) -> void:
	var view_id := "elfie-" + actor_id
	if _observation_view_index_by_id(view_id) >= 0:
		return
	var camera := Camera3D.new()
	camera.fov = 60.0
	camera.near = 0.05
	camera.far = 150.0
	add_child(camera)
	camera.global_position = actor.global_position + Vector3.UP * 0.6 + FOLLOW_CAMERA_OFFSET
	camera.look_at(actor.global_position + Vector3.UP * 0.6)
	_register_observation_view(view_id, "跟随精灵 · " + actor_id, camera, actor.global_position)
	_camera_views[-1]["actor"] = actor
	camera_catalog_revision += 1
	_emit_observer_camera_catalog_changed()


func remove_observer_actor_camera(actor_id: String) -> void:
	var index := _observation_view_index_by_id("elfie-" + actor_id)
	if index < 0:
		return
	var camera := _camera_views[index]["camera"] as Camera3D
	_camera_views.remove_at(index)
	camera.queue_free()
	camera_catalog_revision += 1
	_active_camera_index = _observation_view_index_by_id(_active_camera_id)
	if _active_camera_index < 0 and not _camera_views.is_empty():
		select_observation_view(0)
	_emit_observer_camera_catalog_changed()


func _process(delta: float) -> void:
	_refresh_usage_lighting(delta)
	if Engine.is_editor_hint() or _observer_presentation_paused or _camera_views.is_empty():
		return
	var view := _camera_views[_active_camera_index]
	if not view.has("actor"):
		return
	# Check validity before casting: a freed resident remains a Variant reference.
	if not is_instance_valid(view["actor"]):
		remove_observer_actor_camera(String(view["id"]).trim_prefix("elfie-"))
		return
	var actor := view["actor"] as CharacterBody3D
	if not actor.is_visible_in_tree():
		select_observer_overview()
		return
	var camera := view["camera"] as Camera3D
	var target := actor.global_position + Vector3(0, 0.6, 0)
	var offset: Vector3 = view.get("follow_offset", FOLLOW_CAMERA_OFFSET)
	var desired := target + offset
	# Presentation-only occlusion query: never move the actor or change collisions.
	var query := PhysicsRayQueryParameters3D.create(target, desired)
	query.collision_mask = COLLISION_LAYERS.PERCEPTION_MASK
	var excluded: Array[RID] = [actor.get_rid()]
	for resident in get_tree().get_nodes_in_group(&"runtime_elfie_actors"):
		if resident is CollisionObject3D:
			excluded.append(resident.get_rid())
	query.exclude = excluded
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty():
		desired = (hit["position"] as Vector3).move_toward(target, 0.15)
	var distance := desired.distance_to(target)
	if bool(view.get("follow_initialized", false)):
		var previous_distance := float(view["follow_distance"])
		var speed := 6.0 if distance < previous_distance else 2.0
		distance = move_toward(previous_distance, distance, speed * minf(delta, 0.05))
		target = (view["follow_target"] as Vector3).lerp(target, 1.0 - exp(-8.0 * minf(delta, 0.05)))
	view["follow_initialized"] = true
	view["follow_distance"] = distance
	view["follow_target"] = target
	desired = target + offset.normalized() * distance
	# Smoothing must never carry the camera through the current occluder.
	# Check the final segment from the real resident, not the lagging target.
	query.from = actor.global_position + Vector3(0, 0.6, 0)
	query.to = desired
	var final_hit := get_world_3d().direct_space_state.intersect_ray(query)
	if not final_hit.is_empty():
		desired = (final_hit["position"] as Vector3).move_toward(query.from, 0.25)
		view["follow_distance"] = desired.distance_to(query.from)
	camera.global_position = desired
	camera.look_at(query.from)
	_camera_target = query.from


func observation_view_labels() -> PackedStringArray:
	var labels := PackedStringArray()
	for view in _camera_views:
		labels.append(String(view["label"]))
	return labels


func observer_camera_catalog() -> Dictionary:
	var views: Array[Dictionary] = []
	for view in _camera_views:
		views.append({
			"id": String(view["id"]),
			"label": String(view["label"]),
		})
	# These registered presentation choices share the existing local select transport.
	# They are not physical cameras and never change the active camera identity.
	if _lighting_preview_available:
		for phase: String in ["live", "day", "night", "quiet"]:
			views.append({"id": "lighting-" + phase, "label": phase})
	return {
		"revision": camera_catalog_revision,
		"views": views,
		"active_id": _active_camera_id,
		"presentation_paused": _observer_presentation_paused,
	}


func observation_active_view_index() -> int:
	return _active_camera_index


func observer_presentation_paused() -> bool:
	return _observer_presentation_paused


func set_observation_hud_visible(visible: bool) -> void:
	show_observation_hud = visible
	if _observation_hud != null:
		_observation_hud.visible = visible


func select_observation_view(index: int) -> void:
	if index < 0 or index >= _camera_views.size():
		return
	_active_camera_index = index
	var view := _camera_views[index]
	view["follow_initialized"] = false
	_active_camera_id = String(view["id"])
	var camera := view["camera"] as Camera3D
	camera.current = true
	_camera_target = view["target"] as Vector3
	camera.global_transform = view["transform"] as Transform3D
	camera.size = float(view["size"])
	camera.fov = float(view["fov"])
	if view.has("actor"):
		view["follow_offset"] = FOLLOW_CAMERA_OFFSET
		_process(0.0)
	_sync_orbit_state(camera)
	if view.has("floor_height_limits"): _apply_camera_transform(camera)
	if not _rebuilding and (not _observer_environment.is_empty() or _observer_lighting_preview != "live"):
		_apply_observer_lighting_display()
	if not Engine.is_editor_hint() and _observation_hud != null:
		_observation_hud.call("set_selected_view", index)
	_emit_observer_camera_catalog_changed()


func select_observer_camera_by_id(view_id: String) -> bool:
	if _observer_presentation_paused:
		return false
	if _lighting_preview_available and view_id in ["lighting-live", "lighting-day", "lighting-night", "lighting-quiet"]:
		_observer_lighting_preview = view_id.trim_prefix("lighting-")
		_apply_observer_lighting_display()
		return true
	var index := _observation_view_index_by_id(view_id)
	if index < 0:
		return false
	select_observation_view(index)
	return true


func select_observer_overview() -> bool:
	return select_observer_camera_by_id("overview")


func select_observation_view_named(label_fragment: String) -> bool:
	"""Select the first generated observation camera matching a stable label."""
	for index in range(_camera_views.size()):
		var view := _camera_views[index]
		if String(view["label"]).contains(label_fragment):
			select_observation_view(index)
			return true
	return false


func reset_observation_camera() -> void:
	"""Restore the current preset after direct orbit, pan, or zoom input."""
	_reset_camera()
	_emit_observer_camera_catalog_changed()


func reset_observer_camera() -> void:
	if _observer_presentation_paused:
		return
	reset_observation_camera()


func set_observer_presentation_paused(paused: bool) -> void:
	if _observer_presentation_paused == paused:
		return
	_observer_presentation_paused = paused
	if _observer_water != null:
		_observer_water.set_process(not paused)
	_emit_observer_camera_catalog_changed()


func _observation_view_index_by_id(view_id: String) -> int:
	for index in range(_camera_views.size()):
		var view := _camera_views[index]
		if String(view["id"]) == view_id:
			return index
	return -1


func _emit_observer_camera_catalog_changed() -> void:
	observer_camera_catalog_changed.emit(observer_camera_catalog())


func _cycle_observation_view(direction: int) -> void:
	if _camera_views.is_empty():
		return
	select_observation_view(posmod(_active_camera_index + direction, _camera_views.size()))


func _active_camera() -> Camera3D:
	if _camera_views.is_empty():
		return get_node_or_null("Camera3D") as Camera3D
	return _camera_views[_active_camera_index]["camera"] as Camera3D


func _sync_orbit_state(camera: Camera3D) -> void:
	var offset := camera.global_position - _camera_target
	_camera_distance = maxf(offset.length(), 0.001)
	_camera_yaw = atan2(offset.x, offset.z)
	_camera_pitch = asin(clampf(offset.y / _camera_distance, -1.0, 1.0))


func _viewport_aspect() -> float:
	var viewport_size := get_viewport().get_visible_rect().size
	if viewport_size.x < 1.0 or viewport_size.y < 1.0:
		return 16.0 / 9.0
	return maxf(viewport_size.x / maxf(viewport_size.y, 1.0), 0.1)


func _reset_camera() -> void:
	if _camera_views.is_empty():
		return
	var view := _camera_views[_active_camera_index]
	var camera := view["camera"] as Camera3D
	_camera_target = view["target"] as Vector3
	camera.global_transform = view["transform"] as Transform3D
	camera.size = float(view["size"])
	camera.fov = float(view["fov"])
	if view.has("actor"):
		view["follow_offset"] = FOLLOW_CAMERA_OFFSET
		view["follow_initialized"] = false
		_process(0.0)
	_sync_orbit_state(camera)
	if view.has("floor_height_limits"): _apply_camera_transform(camera)


func _apply_camera_transform(camera: Camera3D) -> void:
	var current_view: Dictionary = _camera_views[_active_camera_index]
	if current_view.has("floor_height_limits"):
		var limits: Vector2 = current_view["floor_height_limits"]
		_camera_target.y = clampf(_camera_target.y,limits.x,limits.y)
		# Bound the orbit itself, not just its resulting position: reversing a
		# drag must respond immediately instead of unwinding an invisible orbit.
		var low := asin(clampf((limits.x-_camera_target.y)/_camera_distance,-1.0,1.0))
		var high := asin(clampf((limits.y-_camera_target.y)/_camera_distance,-1.0,1.0))
		_camera_pitch = clampf(_camera_pitch,maxf(low,deg_to_rad(-35)),minf(high,deg_to_rad(35)))
	var horizontal_scale := cos(_camera_pitch) * _camera_distance
	var offset := Vector3(
		sin(_camera_yaw) * horizontal_scale,
		sin(_camera_pitch) * _camera_distance,
		cos(_camera_yaw) * horizontal_scale
	)
	camera.global_position = _camera_target + offset
	var target_position := _camera_target
	var view_direction := (target_position - camera.global_position).normalized()
	var camera_up := global_transform.basis.y.normalized()
	if absf(view_direction.dot(camera_up)) > 0.98:
		camera_up = -global_transform.basis.x.normalized()
	camera.look_at(target_position, camera_up)
	var view := _camera_views[_active_camera_index]
	if view.has("actor") and is_instance_valid(view["actor"]):
		var actor := view["actor"] as CharacterBody3D
		var actor_target := actor.global_position + Vector3.UP * 0.6
		# Retain the observer's relative view as the resident moves. Right-drag
		# changes that offset while follow continues to aim at the resident.
		view["follow_offset"] = camera.global_position - actor_target
		view["follow_initialized"] = false
		_process(0.0)
		_sync_orbit_state(camera)


func scene_manifest() -> Dictionary:
	return {
		"nest_id": _nest_id,
		"world_revision": world_revision,
		"bed_count": FIXED_BED_COUNT,
		"capabilities": ["semantic_anchors", "complete_actor_sync", "navigation"],
		"zones": _estate_semantics.zones if _estate_semantics != null else [],
		"anchors": _estate_semantics.manifest_anchors(FIXED_BED_COUNT) if _estate_semantics != null else [],
		"facilities": _estate_semantics.facility_descriptors if _estate_semantics != null else [],
	}


func bake_navigation() -> bool:
	if _estate_physics == null or _anchor_markers.size() < 32:
		return false
	if is_instance_valid(_navigation_region):
		return _navigation_region.navigation_mesh.get_polygon_count() > 0
	_navigation_region = _estate_physics.bake(self)
	return _navigation_region!=null and _navigation_region.navigation_mesh.get_polygon_count()>0


func validate_navigation_anchors() -> bool:
	var map := get_world_3d().navigation_map
	_estate_semantics.align_approaches(map)
	var courtyard := resolve_anchor("courtyard/activity")
	if courtyard == null: return false
	for id in semantic_anchor_ids():
		var marker := resolve_anchor(id)
		if marker == null: continue
		var nearest := NavigationServer3D.map_get_closest_point(map, marker.global_position)
		if nearest.distance_to(marker.global_position) > 0.3:
			push_warning("Complete estate approach off navigation: %s at %s, nearest %s" % [id, marker.global_position, nearest])
			return false
		var path := NavigationServer3D.map_get_path(map, marker.global_position, courtyard.global_position, true)
		if path.is_empty() or path[-1].distance_to(courtyard.global_position) > 0.3:
			push_warning("Complete estate disconnected route: %s from %s, partial path %s" % [id, marker.global_position, path])
			return false
	return true


func wait_for_navigation_sync(timeout_seconds: float = 10.0) -> bool:
	# Local geometry readiness only. The authority and read-only presentation
	# use the same synchronization rule, without granting Observer world control.
	var navigation_map := get_world_3d().navigation_map
	var deadline := Time.get_ticks_msec() + int(timeout_seconds * 1000.0)
	while Time.get_ticks_msec() < deadline:
		await get_tree().physics_frame
		var regions := NavigationServer3D.map_get_regions(navigation_map)
		var synchronized := not regions.is_empty()
		# Small landing patches may synchronize before the full baked region.
		for expected: NavigationRegion3D in find_children("*", "NavigationRegion3D", true, false):
			if not regions.has(expected.get_rid()): synchronized = false
		for region: RID in regions:
			if NavigationServer3D.region_get_iteration_id(region) == 0: synchronized = false
		if synchronized and NavigationServer3D.map_get_iteration_id(navigation_map) > 0:
			var anchor_ids := semantic_anchor_ids()
			if anchor_ids.is_empty(): continue
			var marker := resolve_anchor(anchor_ids[0])
			if marker == null or not NavigationServer3D.map_get_closest_point_owner(navigation_map, marker.global_position).is_valid(): continue
			if NavigationServer3D.map_get_closest_point(navigation_map, marker.global_position).distance_to(marker.global_position) > 0.35: continue
			return true
	return false


func configure_estate_path_lighting_review(views: Array[Dictionary]) -> void:
	# Explicit sample: reuse the HUD and camera owner without building a world.
	_camera_views.clear()
	for view: Dictionary in views:
		_add_complete_view(self, str(view["id"]), str(view["focus"]), view["camera"], view["target"], float(view.get("fov", 52.0)))
	camera_catalog_revision += 1
	if not views.is_empty() and str(views[0].id).begins_with("lighting-v4-"):
		_observation_hud.call("set_lighting_views", views)
	else:
		_observation_hud.call("set_views", observation_view_labels(), 0)
	if not _observation_hud.is_connected("view_selected", select_observation_view):
		_observation_hud.connect("view_selected", select_observation_view)
	_observation_hud.visible = true
	select_observation_view(0)


func configure_estate_water_review(views: Array[Dictionary]) -> void:
	_configure_visual_review_views(views)


func configure_estate_event_review(views: Array[Dictionary]) -> void:
	_configure_visual_review_views(views)


func _configure_visual_review_views(views: Array[Dictionary]) -> void:
	_camera_views.clear()
	for view: Dictionary in views:
		var camera := Camera3D.new()
		camera.fov = float(view.get("fov", 52.0))
		camera.near = 0.05
		camera.far = 1000.0
		add_child(camera)
		camera.global_position = view["camera"]
		camera.look_at(view["target"])
		_register_observation_view(view["id"], view["focus"], camera, view["target"])
	if not _observation_hud.is_connected("view_selected", select_observation_view):
		_observation_hud.connect("view_selected", select_observation_view)
	_observation_hud.call("set_views", observation_view_labels())
	_observation_hud.visible = true
	select_observation_view(0)


func configure_collision_review(camera: Camera3D, target: Vector3, labels: PackedStringArray) -> void:
	# Reuse the same selector/orbit/pan/reset; this does not build a world.
	_camera_views.clear()
	for index in range(labels.size()):
		_register_observation_view("collision-review-%d" % index, labels[index], camera, target)
	_observation_hud.set_views(labels, 0)
	if not _observation_hud.view_selected.is_connected(select_observation_view):
		_observation_hud.view_selected.connect(select_observation_view)
	_observation_hud.visible = true
	select_observation_view(0)


func configure_garden_door_review(views: Array[Dictionary]) -> void:
	_camera_views.clear()
	for view: Dictionary in views:
		var camera := Camera3D.new()
		camera.fov = float(view["fov"])
		camera.near = 0.05
		add_child(camera)
		camera.global_position = view["camera"]
		camera.look_at(view["target"])
		_register_observation_view(view["id"], view["focus"], camera, view["target"])
	if not _observation_hud.view_selected.is_connected(select_observation_view):
		_observation_hud.view_selected.connect(select_observation_view)
	_observation_hud.set_views(observation_view_labels(), 0)
	_observation_hud.visible = true
	select_observation_view(0)
