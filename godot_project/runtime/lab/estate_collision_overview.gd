extends Node3D
## Render the exact current runtime shapes; never add or simplify physical geometry.
const ESTATE := preload("res://rooms/estate/estate.tscn")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
var camera_owner: Node3D
var estate: Node3D
var physics: Node3D
var records: Array[Dictionary] = []
var counts: Dictionary = {}
var outdoor_inventory: Array[Dictionary] = []
var _environment: WorldEnvironment
var plant_zones: Node3D
var _appearance: Dictionary = {}
var canopy_hidden_plan := false

func _ready() -> void:
	estate = ESTATE.instantiate() as Node3D
	estate.visible = false
	add_child(estate)
	physics = PHYSICS.new()
	add_child(physics)
	physics.call("build", estate)
	physics.set_physics_process(false)
	var environment := WorldEnvironment.new()
	_environment = environment
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.025, 0.035, 0.055)
	add_child(environment)
	# A true source-model plan view includes restored trees and ground planting.
	# Remove only the sky enclosure that would sit above the aerial camera.
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		if str(mesh.name).begins_with("Transparent large arch") or str(mesh.name) == "ROOF_INNER_SKY_FINAL":
			mesh.visible = false
	for owner: Node3D in [estate, physics]:
		for shape: CollisionShape3D in owner.find_children("*", "CollisionShape3D", true, false):
			if shape.shape == null or shape.disabled:
				continue
			var body := shape.get_parent()
			var module := str(body.get_meta("estate_module", ""))
			var water := str(body.name).begins_with("WaterExclusion_")
			var outdoor := module.is_empty()
			var support := str(body.name) in ["GardenCollision_Terrain", "GardenCollision_Boundary"]
			var category := "water" if water else ("outdoor" if outdoor else module)
			counts[category] = int(counts.get(category, 0)) + 1
			var visual := MeshInstance3D.new()
			visual.mesh = shape.shape.get_debug_mesh()
			var material := StandardMaterial3D.new()
			material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			material.albedo_color = Color(0.1, 0.8, 1.0) if water else (Color(0.4, 1.0, 0.35) if outdoor else Color(1.0, 0.78, 0.3))
			if support:
				material.albedo_color = Color(0.12, 0.19, 0.16)
			visual.material_override = material
			add_child(visual)
			visual.global_transform = shape.global_transform
			records.append({"shape": shape, "visual": visual, "outdoor": outdoor, "support": support})
			if outdoor:
				outdoor_inventory.append({"body": str(body.name), "source": str(body.get_meta("source_node", "")), "shape": shape.shape.get_class(), "bounds": str(shape.global_transform * visual.mesh.get_aabb())})
	plant_zones = load("res://runtime/lab/estate_plant_zones.gd").new()
	add_child(plant_zones)
	plant_zones.call("build", estate)
	plant_zones.visible = false
	for node: Node3D in estate.find_children("*", "Node3D", true, false):
		var tall_outdoor: bool = node is MeshInstance3D and ((node.get_meta("extras", {}) as Dictionary).get("module", "") == "") and ((node as MeshInstance3D).global_transform * (node as MeshInstance3D).get_aabb()).end.y > 4.0
		if node is MultiMeshInstance3D or tall_outdoor:
			_appearance[node] = node.visible
	var views: Array[Dictionary] = [
		{"id": "collision-whole", "focus": "整园全部碰撞 · 外观关闭", "camera": Vector3(18, 52, 35), "target": Vector3(0, 1, 5), "fov": 92.0},
		{"id": "collision-outdoor", "focus": "户外全部碰撞 · 含地面界墙", "camera": Vector3(18, 52, 35), "target": Vector3(0, 1, 5), "fov": 92.0},
		{"id": "collision-outdoor-obstacles", "focus": "户外障碍 · 隐藏地面与外围界墙", "camera": Vector3(18, 42, 35), "target": Vector3(0, 0, 5), "fov": 92.0},
		{"id": "outdoor-real-plan", "focus": "真实俯视 · 含树木与花草", "camera": Vector3(0, 85, 6.01), "target": Vector3(0, 0, 6), "fov": 70.0},
		{"id": "outdoor-plant-zones", "focus": "植物禁行块2米 · 黄树干/红地被/紫灌木", "camera": Vector3(16, 70, 45), "target": Vector3(0, 0, 6), "fov": 90.0},
		{"id": "woodland-plant-zones", "focus": "森林近景 · 拖拽旋转查看空隙", "camera": Vector3(-12, 16, -11), "target": Vector3(0, 0, -24), "fov": 80.0},
		{"id": "woodland-original-planting", "focus": "森林原植物对照 · 含共享低层种植", "camera": Vector3(-16, 5, -18), "target": Vector3(-15, 0.4, -25), "fov": 80.0},
	]
	camera_owner.call("_configure_visual_review_views", views)
	var aerial: Camera3D = camera_owner.get("_camera_views")[3]["camera"]
	aerial.projection = Camera3D.PROJECTION_ORTHOGONAL
	aerial.size = 110.0
	aerial.look_at(Vector3(0, 0, 6), Vector3.FORWARD)
	var aerial_view: Dictionary = camera_owner.get("_camera_views")[3]
	aerial_view["size"] = aerial.size
	aerial_view["transform"] = aerial.global_transform
	camera_owner.connect("observer_camera_catalog_changed", _on_selection)
	print("ESTATE_WHOLE_COLLISION_REVIEW " + JSON.stringify({"shapes": records.size(), "categories": counts, "appearance_visible": false, "navigation_baked": false, "scope": "Exact existing runtime collisions; missing outdoor colliders remain missing"}))
	print("ESTATE_OUTDOOR_COLLIDERS " + JSON.stringify(outdoor_inventory))
	if OS.has_feature("web"):
		canopy_hidden_plan = str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('canopy')||''")) == "0"
		var requested := str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('view')||''"))
		if not requested.is_empty():
			camera_owner.call("select_observer_camera_by_id", requested)

func _on_selection(catalog: Dictionary) -> void:
	var selected := str(catalog.get("active_id", ""))
	var actual_plan := selected == "outdoor-real-plan"
	var original_woodland := selected == "woodland-original-planting"
	var low_planting_only := original_woodland or (actual_plan and canopy_hidden_plan)
	var zones_visible := selected in ["outdoor-plant-zones", "woodland-plant-zones"]
	estate.visible = actual_plan or zones_visible or original_woodland
	plant_zones.visible = zones_visible
	for node: Node3D in _appearance:
		node.visible = bool(_appearance[node]) and not zones_visible
		if low_planting_only:
			var group := str(node.get_meta("source_group",""))
			var number := group.trim_prefix("__ELFIE_INST_GROUP_").to_int()
			node.visible = bool(_appearance[node]) and node is MultiMeshInstance3D and ((number >= 52 and number <= 81) or (number >= 88 and number <= 132))
	_environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_environment.environment.ambient_light_color = Color(0.8, 0.85, 0.9)
	_environment.environment.ambient_light_energy = 0.65 if actual_plan or zones_visible or original_woodland else 0.0
	var outdoor_only := selected != "collision-whole"
	for entry: Dictionary in records:
		var shape := entry["shape"] as CollisionShape3D
		(entry["visual"] as MeshInstance3D).visible = false if original_woodland else (str(shape.get_parent().name).begins_with("WaterExclusion_") if zones_visible else (not actual_plan and (not outdoor_only or bool(entry["outdoor"])) and not (selected == "collision-outdoor-obstacles" and bool(entry["support"]))))
		if actual_plan and canopy_hidden_plan:
			(entry["visual"] as MeshInstance3D).visible = str(shape.get_parent().name) == "GardenCollision_TreeTrunks"
