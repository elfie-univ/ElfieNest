extends Node3D
## Local double-leaf animation candidate fitted to the real empty garden portal.

const SOURCE := "res://rooms/estate/ElfieNest-complete-final.glb"
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const DOOR := preload("res://rooms/estate/estate_door.gd")
const GARDEN_DOOR := preload("res://rooms/estate/estate_garden_door.gd")
const CONTEXT := ["Central L1 curved front glass", "Central L1 fitted panoramic reveal", "Central L1 rounded garden entrance", "Central L1 fitted complete floor", "Central single continuous full-height envelope", "Flower preview | CY R002 curved entrance lower tread", "Flower preview | CY R002 curved entrance upper tread", "Flower preview | CY R003 reference seven-petal stone and ring-material connector"]
var camera_owner: Node3D
var source_frame: MeshInstance3D
var source_leaf_count := 0
var source_materials: Array[Dictionary] = []
var opening_bounds := AABB()
var leaves: Array[Dictionary] = []
var views: Array[Dictionary] = []
var counts: Dictionary = {}
var _controls: Array[RefCounted] = []
var _probe: Node3D
var _elapsed := 0.0
var _report_elapsed := 0.0
var _phase := "closed"


static func is_requested() -> bool:
	return OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('mode')")) == "garden_door_review"


func _ready() -> void:
	build()


func build() -> void:
	var geometry := Node3D.new()
	geometry.name = "RealGardenEntranceContext"
	add_child(geometry)
	var source := (load(SOURCE) as PackedScene).instantiate() as Node3D
	source.visible = false
	add_child(source)
	var front_glass: MeshInstance3D
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		if bool((mesh.get_meta("extras", {}) as Dictionary).get("door_leaf", false)):
			source_leaf_count += 1
		if str(mesh.name) not in CONTEXT:
			continue
		if str(mesh.name) == "Central L1 rounded garden entrance":
			source_frame = mesh
		if str(mesh.name) == "Central L1 curved front glass":
			front_glass = mesh
		mesh.reparent(geometry, true)
		mesh.visible = true
	for sun: DirectionalLight3D in source.find_children("*", "DirectionalLight3D", true, false):
		sun.reparent(geometry, true)
		sun.visible = true
	source.free()
	if source_frame == null or front_glass == null:
		push_error("Garden review requires the real portal and facade glazing")
		return
	for mesh: MeshInstance3D in [source_frame, front_glass]:
		var material := mesh.mesh.surface_get_material(0) as BaseMaterial3D
		source_materials.append({"source": material, "albedo": material.albedo_color, "energy": material.emission_energy_multiplier})
	DAYLIGHT.apply(geometry)
	var generated: Dictionary = GARDEN_DOOR.new().build(self, source_frame, front_glass, false)
	opening_bounds = generated["opening_bounds"]
	leaves = generated["leaves"]
	for door: Dictionary in leaves:
		_controls.append(DOOR.new(door))
	_probe = Node3D.new()
	_probe.name = "LocalProximityAnimationProbe"
	add_child(_probe)
	var target := opening_bounds.get_center()
	views = [
		{"id": "garden-door-cycle", "focus": "中央室外门 · 双扇开关动画候选", "camera": target + Vector3(2.8, 1.6, 6.0), "target": target, "fov": 58.0},
		{"id": "garden-door-closed", "focus": "中央室外门 · 闭合轮廓候选", "camera": target + Vector3(2.8, 1.6, 6.0), "target": target, "fov": 58.0},
	]
	counts = {"authority": false, "shape_approved": true, "source_frame": str(source_frame.name), "original_authored_leaves": source_leaf_count, "new_candidate_leaves": leaves.size(), "opening_size": [opening_bounds.size.x, opening_bounds.size.y, opening_bounds.size.z], "scope": "Shared approved leaf geometry; local animation probe only; no world day/night input"}
	var reference := (load("res://rooms/nest.tscn") as PackedScene).instantiate()
	var environment := reference.get_node("WorldEnvironment") as WorldEnvironment
	reference.remove_child(environment)
	reference.free()
	add_child(environment)
	if camera_owner != null:
		camera_owner.call("configure_garden_door_review", views)
	advance_preview(0.0, false)
	_publish()


func advance_preview(delta: float, nearby: bool) -> void:
	if _probe == null:
		return
	_probe.global_position = opening_bounds.get_center() - Vector3.UP * 1.2 if nearby else Vector3(40.0, 0.0, 40.0)
	var actors: Array[Node3D] = [_probe]
	for control: RefCounted in _controls:
		control.advance(delta, false, actors)


func _process(delta: float) -> void:
	if leaves.is_empty():
		return
	if camera_owner != null and bool(camera_owner.call("observer_presentation_paused")):
		return
	_elapsed += maxf(delta, 0.0)
	var cycle := fmod(_elapsed, 8.0)
	var nearby := cycle >= 1.0 and cycle < 4.0
	if camera_owner != null:
		var catalog := camera_owner.call("observer_camera_catalog") as Dictionary
		if str(catalog.get("active_id", "")) == "garden-door-closed":
			nearby = false
	advance_preview(delta, nearby)
	_phase = "approach-open" if nearby else ("departure-hold" if cycle < 6.0 and cycle >= 4.0 else "closed")
	_report_elapsed += delta
	if _report_elapsed >= 0.4:
		_report_elapsed = 0.0
		_publish()


func _publish() -> void:
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.__gardenDoorReview=" + JSON.stringify({"counts": counts, "phase": _phase, "amounts": leaves.map(func(leaf: Dictionary) -> float: return float(leaf["amount"])), "authority": false}))
