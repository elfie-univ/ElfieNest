extends Node3D
## Explicit local effect review. This never receives or fabricates world events.

const SOURCE := "res://rooms/estate/ElfieNest-complete-final.glb"
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const LIGHTING := preload("res://rooms/estate/estate_lighting.gd")
const SEMANTICS := preload("res://rooms/estate/estate_semantics.gd")
const EFFECTS := preload("res://runtime/lab/estate_event_effects.gd")
const SLEEPING_BODY := preload("res://characters/tovren/tovren.tscn")
const SLEEP_REVIEW := preload("res://runtime/lab/estate_sleep_review.gd")
const PLATFORM_CYCLE := preload("res://runtime/lab/estate_platform_cycle.gd")
var camera_owner: Node3D
var review_geometry: Node3D
var effects: Node3D
var views: Array[Dictionary] = []
var counts: Dictionary = {}
var arrival_materials: Array[Dictionary] = []
var platform_cycle: Node3D
var stair_target := Vector3.ZERO
var arrival_lighting: Node3D
var ordinary: RefCounted
var _elapsed := 0.0
var _report_elapsed := 0.0
var _last_logged_cover_phase := ""


static func is_requested() -> bool:
	if not OS.has_feature("web"):
		return false
	return str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('mode')")) == "event_review"


func _ready() -> void:
	build()


func build() -> void:
	review_geometry = Node3D.new()
	review_geometry.name = "AuthoredBedAndArrivalSurroundings"
	add_child(review_geometry)
	var source := (load(SOURCE) as PackedScene).instantiate() as Node3D
	source.visible = false
	add_child(source)
	var bed: MeshInstance3D
	var bed_shells: Array[MeshInstance3D] = []
	var arrival_floor: MeshInstance3D
	var arrival_platform: MeshInstance3D
	var platform_steps: MeshInstance3D
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		var extras := mesh.get_meta("extras", {}) as Dictionary
		var module := str(extras.get("module", ""))
		if module != "M01" and not (module == "central" and (int(extras.get("floor", 1)) == 4 or str(mesh.name).begins_with("Central single continuous full-height envelope"))):
			continue
		if module == "M01" and str(extras.get("piece", "")) == "bed_cover" and str(extras.get("resident", "")) == "A":
			bed = mesh
		if module == "M01" and str(extras.get("resident", "")) == "A" and str(extras.get("assembly", "")) == "bed" and str(extras.get("piece", "")) in ["shell", "rolled_lip", "deck"]:
			bed_shells.append(mesh)
		if module == "central" and str(mesh.name).begins_with("Central L4 round arrival floor"):
			arrival_floor = mesh
		if module == "central" and str(mesh.name).begins_with("Roof01 complete raised landing platform"):
			arrival_platform = mesh
		if module=="central" and extras.get("assembly")=="roof01_steps":
			platform_steps=mesh
		mesh.reparent(review_geometry, true)
		mesh.visible = true
		if module == "M01" and str(extras.get("resident", "")) == "A" and str(extras.get("piece", "")) == "throw":
			mesh.visible = false
	for light: DirectionalLight3D in source.find_children("*", "DirectionalLight3D", true, false):
		light.reparent(review_geometry, true)
		light.visible = true
	source.free()
	if bed == null or bed_shells.size() != 3 or arrival_floor == null or arrival_platform == null:
		push_error("Event review requires the actual M01 A bed and central arrival floor")
		return
	DAYLIGHT.apply(review_geometry)
	ordinary = LIGHTING.new()
	ordinary.bind(review_geometry)
	ordinary.apply(false)
	var semantics := SEMANTICS.new()
	semantics.build(self, review_geometry)
	_add_sleeping_body(semantics.anchors.get("dorm-01/bed-01") as Marker3D)
	var sleep := SLEEP_REVIEW.new()
	sleep.name = "SleepPresentation"
	add_child(sleep)
	sleep.bind(get_node("LocalSleepingBody"), bed, camera_owner)
	var arrival := semantics.anchors.get("central-04/activity") as Marker3D
	if arrival == null:
		push_error("Event review has no source-bound central-04/activity anchor")
		return
	effects = EFFECTS.new()
	effects.name = "LocalEffectCandidates"
	add_child(effects)
	var shell := bed_shells.filter(func(mesh: MeshInstance3D) -> bool: return str((mesh.get_meta("extras", {}) as Dictionary).get("piece", "")) == "shell")[0] as MeshInstance3D
	var shell_frame := shell.global_transform
	var shell_bounds := shell.get_aabb()
	var shell_points := PackedVector3Array()
	var crown_points := PackedVector3Array()
	for part: MeshInstance3D in bed_shells:
		var local_frame := shell_frame.affine_inverse() * part.global_transform
		shell_bounds = shell_bounds.merge(local_frame * part.get_aabb())
		for surface in range(part.mesh.get_surface_count()):
			var vertices: PackedVector3Array = part.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			for vertex: Vector3 in vertices:
				shell_points.append(local_frame * vertex)
				if str((part.get_meta("extras", {}) as Dictionary).get("piece", "")) == "rolled_lip":
					crown_points.append(local_frame * vertex)
	effects.configure_bed(shell_frame, shell_bounds, shell_points, crown_points)
	var platform_bounds := arrival_platform.global_transform * arrival_platform.get_aabb()
	# The semantic activity marker identifies this apparatus; the source platform
	# surface, not the lower room floor, determines the visible effect height.
	var arrival_surface := Vector3(arrival.global_position.x, platform_bounds.end.y + 0.025, arrival.global_position.z)
	var radius := minf(1.1, minf(platform_bounds.size.x, platform_bounds.size.z) * 0.25)
	effects.configure_arrival(arrival_surface, radius)
	assert(platform_steps!=null,"Arrival must face the actual platform steps")
	stair_target=(platform_steps.global_transform*platform_steps.get_aabb()).get_center()
	_bind_arrival_materials()
	var cover := effects.get_node("BedEffect/GlassDome") as MeshInstance3D
	var bed_target := (cover.global_transform * cover.get_aabb()).get_center()
	var floor_mesh := semantics.room_floors["M01"] as MeshInstance3D
	var room_center := (floor_mesh.global_transform * floor_mesh.get_aabb()).get_center()
	var bed_camera := bed_target + (Vector3(room_center.x, bed_target.y + 0.85, room_center.z) - bed_target) * 1.12
	views = [
		{"id": "C02-bed-cover", "focus": "实体具身 · 接管地球机器人，身体留床", "target": bed_target, "camera": bed_camera, "fov": 70.0},
		{"id": "C04-arrival", "focus": "领养到达 → 走下机台（审阅循环）", "target": arrival_surface+Vector3.UP*0.95, "camera": arrival_surface + Vector3(stair_target.x-arrival_surface.x,0,stair_target.z-arrival_surface.z).normalized()*5.0+Vector3.UP*1.55, "fov":100.0},
	]
	for choice: Array in [["sleep-back", "正躺 · 原被盖上与回铺"], ["sleep-left", "左侧躺 · 原被盖上与回铺"], ["sleep-right", "右侧躺 · 原被盖上与回铺"]]:
		views.append({"id": choice[0], "focus": choice[1], "target": bed_target, "camera": bed_target+(bed_camera-bed_target)*1.25, "fov": 70.0})
	counts = {"bed_module": "M01", "bed_resident": "A", "bed_source": str(shell.name), "bed_shell_parts": bed_shells.size(), "body_fixture": "local-existing-sleeping-pose", "arrival_anchor": "central-04/activity", "arrival_source": str(arrival_platform.name), "geometry_meshes": review_geometry.find_children("*", "MeshInstance3D", true, false).size(), "authority": false}
	var reference := (load("res://rooms/nest.tscn") as PackedScene).instantiate()
	var environment := reference.get_node("WorldEnvironment") as WorldEnvironment
	reference.remove_child(environment)
	reference.free()
	add_child(environment)
	if OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('lighting')||''"))=="night":
		apply_arrival_night()
	if camera_owner != null:
		platform_cycle = PLATFORM_CYCLE.new()
		platform_cycle.name = "LocalPlatformAnimation"
		add_child(platform_cycle)
		var walking_surfaces: Array[MeshInstance3D] = [arrival_platform,platform_steps,arrival_floor]
		platform_cycle.call("bind", effects, platform_bounds, Callable(self, "_update_arrival_materials"),stair_target,walking_surfaces)
		camera_owner.call("configure_estate_event_review", views)
		if OS.has_feature("web"):
			var selected := str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('view')||'C02-bed-cover'"))
			camera_owner.call("select_observer_camera_by_id", selected)
	_publish()
	print("ESTATE_EVENT_REVIEW ", JSON.stringify(counts))


func apply_arrival_night() -> void:
	# The picker uses the same confirmed night setup as the standalone review.
	if bool(arrival_lighting.get("night")): return
	arrival_lighting.set("night",true)
	ordinary.apply(true)
	for sun: DirectionalLight3D in review_geometry.find_children("*","DirectionalLight3D",true,false): sun.light_energy*=0.14
	var environment := get_node("WorldEnvironment") as WorldEnvironment
	environment.environment=environment.environment.duplicate(true)
	environment.environment.background_color=Color(0.025,0.035,0.065)
	environment.environment.ambient_light_energy=0.28
	environment.environment.background_energy_multiplier=0.3


func _process(delta: float) -> void:
	if effects == null:
		return
	if camera_owner != null and bool(camera_owner.call("observer_presentation_paused")):
		return
	_elapsed += delta
	var view_id := "C02-bed-cover"
	if camera_owner != null:
		view_id = str((camera_owner.call("observer_camera_catalog") as Dictionary).get("active_id", ""))
	sample_cover_view(view_id,_elapsed)
	if platform_cycle != null:
		platform_cycle.call("sample", _elapsed)
	else:
		effects.preview_arrival(fmod(_elapsed, 6.0))
		_update_arrival_materials(fmod(_elapsed, 6.0))
	_report_elapsed += delta
	if _report_elapsed >= 0.5:
		_report_elapsed = 0.0
		_publish()


func sample_cover_view(view_id: String, seconds: float) -> void:
	# A resting body pose alone is not the external-body/robot embodiment mode.
	# This local visual selector does not own or change the real mode transition.
	effects.preview_cover(fposmod(seconds,7.0) if view_id=="C02-bed-cover" else 6.0)


func _publish() -> void:
	if not OS.has_feature("web") or effects == null:
		return
	var report := {"counts": counts, "elapsed": _elapsed, "cover_phase": effects.get("cover_phase"), "arrival_phase": effects.get("arrival_phase"), "platform_animation_stage": platform_cycle.get("animation_stage") if platform_cycle != null else "standalone_effect", "authority": false, "limitations": ["Local sleeping-pose fixture and cover animation only; no world resident or transport state is implied"]}
	JavaScriptBridge.eval("window.__estateEventReview=" + JSON.stringify(report))
	var phase := str(effects.get("cover_phase"))
	if phase != _last_logged_cover_phase:
		_last_logged_cover_phase = phase
		var dome := effects.get_node("BedEffect/GlassDome") as MeshInstance3D
		var material := dome.material_override as ShaderMaterial
		var level := float(material.get_shader_parameter("cover_level"))
		var bounds := dome.global_transform * dome.get_aabb()
		var camera := get_viewport().get_camera_3d()
		var diagnostic := {
			"phase": phase, "elapsed": _elapsed,
			"visible": dome.visible, "visible_in_tree": dome.is_visible_in_tree(),
			"alpha": float(material.get_shader_parameter("edge_opacity")) * level,
			"face_alpha": float(material.get_shader_parameter("face_opacity")) * level,
			"cover_level": level,
			"world_bounds_min": _coordinates(bounds.position),
			"world_bounds_max": _coordinates(bounds.end),
			"frame_determinant": dome.global_basis.determinant(),
			"mesh_layers": dome.layers,
		}
		if camera != null:
			diagnostic["camera_position"] = _coordinates(camera.global_position)
			diagnostic["camera_in_cover_aabb"] = bounds.has_point(camera.global_position)
			diagnostic["camera_local_to_cover"] = _coordinates(dome.to_local(camera.global_position))
			diagnostic["camera_cull_mask"] = camera.cull_mask
			diagnostic["center_in_frustum"] = camera.is_position_in_frustum(bounds.get_center())
		print("ESTATE_COVER_DIAGNOSTIC ", JSON.stringify(diagnostic))


static func _coordinates(point: Vector3) -> Array[float]:
	return [point.x, point.y, point.z]


func _bind_arrival_materials() -> void:
	arrival_lighting=load("res://runtime/lab/estate_arrival_lighting.gd").new()
	arrival_lighting.name="CoordinatedArrivalLighting"
	add_child(arrival_lighting)
	arrival_lighting.call("bind",review_geometry)
	arrival_materials.assign(arrival_lighting.get("bindings"))


func _update_arrival_materials(seconds: float) -> void:
	arrival_lighting.call("sample",seconds)


func _add_sleeping_body(marker: Marker3D) -> void:
	if marker == null:
		push_error("Cover animation review needs the actual M01 A bed contact")
		return
	# Reuse the existing Actor's sleeping pose on the actual bed. This fixture has
	# no world identity, navigation command, network connection or resident binding.
	var body := SLEEPING_BODY.instantiate() as ElfieActor
	body.name = "LocalSleepingBody"
	body.set_meta("local_visual_sample", true)
	add_child(body)
	body.remove_from_group(&"runtime_elfie_actors")
	body.configure("local-cover-sleeping-fixture", marker.global_position)
	body.set_physics_process(false)
	var error := body.enter_furniture(marker, "dorm-01/bed-01")
	if not error.is_empty():
		push_error("Existing local sleeping pose could not meet the real bed: " + error)
