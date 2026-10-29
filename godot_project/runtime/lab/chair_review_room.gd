extends Node3D
## Exact M01 ground-floor meshes only. Uses the production collision builder.

const SOURCE := "res://rooms/estate/ElfieNest-complete-final.glb"
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const SEMANTICS := preload("res://rooms/estate/estate_semantics.gd")
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
var semantics: RefCounted
var geometry: Node3D
var physics: Node3D
var navigation: NavigationRegion3D
var swivel: Node3D


func configure_swivel() -> Node3D:
	if is_instance_valid(swivel): return swivel
	# Preserve the recess with a conservative compound footprint, not one
	# hull across the gap or thousands of coplanar contact triangles.
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		var e: Dictionary = mesh.get_meta("extras", {})
		if e.get("resident") != "A" or e.get("assembly") != "desk" or e.get("piece") != "worktop": continue
		var replacement := preload("res://runtime/lab/chair_desktop_collision.gd").create(mesh)
		if replacement == null:
			push_error("Original desktop silhouette could not be preserved")
			return null
		for body: StaticBody3D in physics.find_children("*", "StaticBody3D", true, false):
			if String(body.get_meta("source_node", "")) == String(mesh.name):
				body.free()
				break
		physics.add_child(replacement)
		replacement.global_transform = mesh.global_transform
	var marker := semantics.anchors["dorm-01/chair-01"] as Marker3D
	swivel = preload("res://runtime/lab/chair_review_swivel.gd").new()
	geometry.add_child(swivel)
	swivel.install(geometry, physics, marker.get_meta("interaction_transform") as Transform3D)
	return swivel


func build() -> Dictionary:
	geometry = Node3D.new()
	geometry.name = "OriginalM01GroundFloor"
	add_child(geometry)
	# Instantiate the raw import, not estate.tscn: no full-site effects/sidecars.
	var source := (load(SOURCE) as PackedScene).instantiate() as Node3D
	source.visible = false
	add_child(source)
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		var extras: Dictionary = mesh.get_meta("extras", {})
		if extras.get("module") == "M01" and int(extras.get("floor", 0)) == 1:
			mesh.reparent(geometry, true)
			mesh.visible = true
	source.free()
	DAYLIGHT.apply(geometry)
	physics = PHYSICS.new()
	add_child(physics)
	physics.build(geometry)
	semantics = SEMANTICS.new()
	semantics.build(self, geometry)
	navigation = physics.bake(self)
	var map := get_world_3d().navigation_map
	for _frame in range(20):
		await get_tree().physics_frame
		if NavigationServer3D.map_get_iteration_id(map) > 0:
			break
	semantics.align_approaches(map)
	return {
		"ready": semantics.anchors.has("dorm-01/chair-01") and navigation.navigation_mesh.get_polygon_count() > 0,
		"meshes": geometry.get_child_count(), "colliders": physics.collider_count,
		"polygons": navigation.navigation_mesh.get_polygon_count(),
	}
