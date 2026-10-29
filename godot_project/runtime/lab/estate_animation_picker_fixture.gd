extends Node3D
## Disposable crop of actual source meshes; all mutations die with this fixture.
const SOURCE := preload("res://rooms/estate/ElfieNest-complete-final.glb")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const CATALOG := preload("res://runtime/lab/estate_animation_picker_catalog.gd")
var geometry: Node3D
var _estate_physics: Node3D
var _estate_semantics: RefCounted
var navigation: NavigationRegion3D
signal fixture_frame
signal fixture_physics_frame

func _process(_delta: float) -> void: fixture_frame.emit()
func _physics_process(_delta: float) -> void: fixture_physics_frame.emit()

func build(id: String) -> String:
	var generated := Node3D.new()
	generated.name = "Generated"
	add_child(generated)
	geometry = Node3D.new()
	geometry.name = "CompleteEstate"
	generated.add_child(geometry)
	var source := SOURCE.instantiate() as Node3D
	source.visible = false
	add_child(source)
	var water := id in ["fountain", "spillway", "lake", "water-night"]
	if water: preload("res://rooms/estate/estate_water.gd").attach(source)
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		if PHYSICS.is_instancing_template(mesh) and not (water and str(mesh.name)=="__ELFIE_INST_GROUP_133"): continue
		var extra := mesh.get_meta("extras", {}) as Dictionary
		var module := str(extra.get("module", ""))
		if (water and not module.is_empty()) or (not water and not CATALOG.modules(id).has(module)): continue
		# M01 sleep/desk samples need only their actual ground floor.
		if module == "M01" and not id.begins_with("sofa-") and int(extra.get("floor",1))!=1: continue
		mesh.reparent(geometry, true)
		mesh.visible = not str(mesh.name).begins_with("__ELFIE_INST_GROUP_")
		for surface in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface)
			if material != null: mesh.set_surface_override_material(surface, material.duplicate())
	for light: DirectionalLight3D in source.find_children("*", "DirectionalLight3D", true, false):
		light.reparent(geometry, true)
		light.visible = true
	source.free()
	preload("res://rooms/estate/estate_daylight.gd").apply(geometry)
	var reference := (load("res://rooms/nest.tscn") as PackedScene).instantiate()
	var environment := reference.get_node("WorldEnvironment") as WorldEnvironment
	reference.remove_child(environment)
	reference.free()
	environment.environment = environment.environment.duplicate(true)
	add_child(environment)
	_estate_physics = PHYSICS.new()
	add_child(_estate_physics)
	if not water: _estate_physics.build(geometry)
	if id.begins_with("sofa-"):
		preload("res://runtime/lab/estate_tour_room.gd").configure_sofa_collision(geometry,_estate_physics)
	_estate_semantics = preload("res://rooms/estate/estate_semantics.gd").new()
	_estate_semantics.build(self, geometry)
	if CATALOG.needs_navigation(id):
		navigation = _estate_physics.bake(self)
		if navigation == null: return "Local navigation is missing"
		for frame in range(120):
			await fixture_physics_frame
			await fixture_frame
			if NavigationServer3D.map_get_iteration_id(get_world_3d().navigation_map)==0: continue
			if NavigationServer3D.region_get_iteration_id(navigation.get_rid())>0:
				var sample := resolve_anchor("dorm-01/bed-01" if id == "chair" or id.begins_with("sleep-") or id=="embodiment" else "central-01/activity")
				if sample != null:
					var nearest := NavigationServer3D.map_get_closest_point(get_world_3d().navigation_map, sample.global_position)
					if absf(nearest.y-sample.global_position.y)<0.16 and nearest.distance_to(sample.global_position)<0.5: break
		_estate_semantics.align_approaches(get_world_3d().navigation_map)
	return ""

func resolve_anchor(id: String) -> Marker3D:
	return _estate_semantics.anchors.get(id) as Marker3D
