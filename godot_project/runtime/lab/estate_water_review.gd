extends Node3D
## Explicit visual review of authored water; never starts a semantic world.

const SOURCE := "res://rooms/estate/ElfieNest-complete-final.glb"
const WATER := preload("res://rooms/estate/estate_water.gd")
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const LIGHTING := preload("res://rooms/estate/estate_lighting.gd")
const CANDIDATES := preload("res://runtime/lab/estate_water_candidates.gd")
const SPLASH := preload("res://runtime/lab/estate_fountain_splash.gd")

var camera_owner: Node3D
var review_geometry: Node3D
var counts: Dictionary = {}
var views: Array[Dictionary] = []
var candidates: Node3D
var splash: Node3D
var _elapsed := 0.0


static func is_requested() -> bool:
	if not OS.has_feature("web"):
		return false
	return str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('mode')")) == "water_review"


func _ready() -> void:
	build()


func build() -> void:
	review_geometry = Node3D.new()
	review_geometry.name = "AuthoredWaterAndSurroundings"
	add_child(review_geometry)
	var source := (load(SOURCE) as PackedScene).instantiate() as Node3D
	source.visible = false
	add_child(source)
	counts = WATER.attach(source)
	views = review_views(source)
	# Capture actual contacts and the shared spray resource before the crop
	# discards source templates. This local candidate does not alter the estate.
	splash = SPLASH.new()
	splash.name = "LocalFountainContactSplash"
	add_child(splash)
	var splash_inventory: Dictionary = splash.call("bind", source)
	print("ESTATE_FOUNTAIN_SPLASH ", JSON.stringify(splash_inventory))
	# Keep the real pool/shore geometry around the three close views. This is
	# an explicit review crop, not a production asset or density change.
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or String(mesh.name).begins_with("__ELFIE_INST_GROUP_"):
			continue
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if not String(extras.get("module", "")).is_empty():
			continue
		var bounds := mesh.global_transform * mesh.get_aabb()
		var selected := false
		for view: Dictionary in views:
			if (view["bounds"] as AABB).grow(2.0).intersects(bounds) or (view["meshes"] as Array).has(mesh):
				selected = true
				break
		if selected:
			mesh.reparent(review_geometry, true)
			mesh.visible = true
	for light: DirectionalLight3D in source.find_children("*", "DirectionalLight3D", true, false):
		light.reparent(review_geometry, true)
		light.visible = true
	source.free()
	DAYLIGHT.apply(review_geometry)
	var ordinary := LIGHTING.new()
	ordinary.bind(review_geometry)
	ordinary.apply(false)
	counts = WATER.attach(review_geometry)
	var reference := (load("res://rooms/nest.tscn") as PackedScene).instantiate()
	var environment := reference.get_node("WorldEnvironment") as WorldEnvironment
	reference.remove_child(environment)
	reference.free()
	add_child(environment)
	candidates = CANDIDATES.new()
	add_child(candidates)
	candidates.call("bind", review_geometry, environment.environment)
	camera_owner.call("configure_estate_water_review", views)
	if OS.has_feature("web"):
		var selected := str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('view')||'D01-fountain'"))
		camera_owner.call("select_observer_camera_by_id", selected)
		JavaScriptBridge.eval("window.__estateWaterReview=" + JSON.stringify({"counts": counts, "views": ["D01-fountain", "D02-spillway-seam", "D03-lake-shore", "D03-lake-full", "D04-fountain-night", "D05-lake-night"], "geometry_meshes": review_geometry.find_children("*", "MeshInstance3D", true, false).size(), "authority": false, "limitations": ["Local whole-lake and night-color animation candidates; no world day phase or music linkage; visual approval pending"]}))
	print("ESTATE_WATER_REVIEW ", JSON.stringify(counts))


static func review_views(estate: Node3D) -> Array[Dictionary]:
	var fountain: Array[MeshInstance3D] = []
	var spillway: Array[MeshInstance3D] = []
	var lake: Array[MeshInstance3D] = []
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.mesh.get_surface_count() == 0:
			continue
		var material := mesh.get_active_material(0)
		if material == null or not material.has_meta("estate_water_role"):
			continue
		var role := str(material.get_meta("estate_water_role"))
		if role in ["jet", "ripple", "foam"] or str(mesh.name) == "Reference fountain water":
			fountain.append(mesh)
		elif role == "spillway" or str(mesh.name) == "COMPLETE Inset natural lake receiving under spillway":
			spillway.append(mesh)
		elif str(mesh.name) == "COMPLETE Inset natural lake":
			lake.append(mesh)
	var close_lake := _view("D03-lake-shore", "湖面近景：波纹、反光与岸边", lake, Vector3(0.14, 0.12, 0.17))
	var full_lake: Dictionary = close_lake.duplicate()
	full_lake["id"] = "D03-lake-full"
	full_lake["focus"] = "整片湖面：多尺度波光候选"
	# Stay below the authored sky roof and inside its R50 enclosure.
	# Wide FOV frames the whole lake in both landscape and narrow review panels.
	full_lake["fov"] = 76.0
	full_lake["camera"] = (full_lake["target"] as Vector3) + Vector3(0.0, 30.0, 8.0)
	var pool: MeshInstance3D
	for mesh: MeshInstance3D in fountain:
		if str(mesh.name) == "Reference fountain water":
			pool = mesh
	var pool_bounds := pool.global_transform * pool.get_aabb()
	var pool_parts: Array[MeshInstance3D] = []
	for mesh: MeshInstance3D in fountain:
		var center := (mesh.global_transform * mesh.get_aabb()).get_center()
		if center.x >= pool_bounds.position.x and center.x <= pool_bounds.end.x and center.z >= pool_bounds.position.z and center.z <= pool_bounds.end.z:
			pool_parts.append(mesh)
	var night_lake := full_lake.duplicate()
	night_lake["id"]="D05-lake-night"
	night_lake["focus"]="夜景全览：自然湖面与喷泉环光"
	# One oblique review framing includes both actual pool and lake.
	var combined := (full_lake["bounds"] as AABB).merge(pool_bounds)
	night_lake["target"]=combined.get_center()
	night_lake["camera"]=combined.get_center()+Vector3(0,21,19)
	night_lake["fov"]=72.0
	return [
		_view("D01-fountain", "喷泉：喷流、落水与涟漪", fountain, Vector3(0.9, 0.65, 1.0)),
		_view("D02-spillway-seam", "溢流：入口、落水与接缝", spillway, Vector3(0.9, 0.7, 1.0)),
		close_lake,
		full_lake,
		_view("D04-fountain-night", "夜间喷泉：原水柱发光与池内逐圈环光", pool_parts, Vector3(0.9, 0.65, 1.0)),
		night_lake,
	]


static func _view(id: String, focus: String, meshes: Array[MeshInstance3D], direction: Vector3) -> Dictionary:
	var bounds := AABB()
	var initialized := false
	for mesh in meshes:
		var actual := mesh.global_transform * mesh.get_aabb()
		bounds = bounds.merge(actual) if initialized else actual
		initialized = true
	bounds = bounds.grow(0.05) if initialized else bounds
	var target := bounds.get_center()
	var span := maxf(bounds.size.x, maxf(bounds.size.y, bounds.size.z))
	return {"id": id, "focus": focus, "meshes": meshes, "bounds": bounds, "target": target, "camera": target + direction * maxf(span, 1.0)}


func _process(delta: float) -> void:
	if candidates == null or camera_owner == null or bool(camera_owner.call("observer_presentation_paused")):
		return
	_elapsed += delta
	var view_id := str(camera_owner.get("_active_camera_id"))
	splash.call("sample", _elapsed)
	splash.visible = view_id in ["D01-fountain", "D04-fountain-night", "D05-lake-night"]
	var night := view_id in ["D04-fountain-night","D05-lake-night"]
	candidates.call("sample", _elapsed, night)
