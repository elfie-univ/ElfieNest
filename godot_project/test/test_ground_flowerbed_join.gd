extends SceneTree
## Check the actual imported ground at the flowerbed-to-ring junction.

const GROUND := "res://nest/courtyard/parts/ground/shared-ground.glb"

func _initialize() -> void:
	call_deferred("run")

static func material_at(meshes: Array[Mesh], x: float, z: float) -> String:
	var maximum := -INF
	var result := ""
	for mesh:Mesh in meshes:
		for surface: int in mesh.get_surface_count():
			var arrays := mesh.surface_get_arrays(surface)
			var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			for offset: int in range(0, indices.size(), 3):
				var a := positions[indices[offset]]
				var b := positions[indices[offset + 1]]
				var c := positions[indices[offset + 2]]
				var denominator := (b.z-c.z)*(a.x-c.x)+(c.x-b.x)*(a.z-c.z)
				if absf(denominator) < 0.0000000001: continue
				var u := ((b.z-c.z)*(x-c.x)+(c.x-b.x)*(z-c.z))/denominator
				var v := ((c.z-a.z)*(x-c.x)+(a.x-c.x)*(z-c.z))/denominator
				if minf(minf(u, v), 1.0-u-v) < -0.000001: continue
				var height := u*a.y+v*b.y+(1.0-u-v)*c.y
				if height <= maximum: continue
				maximum = height
				result = mesh.surface_get_material(surface).resource_name.to_lower()
	return result

static func validate_library(scene: Node3D) -> String:
	var bodies:Array[Mesh]=[]
	for node:MeshInstance3D in scene.find_children("*","MeshInstance3D",true,false):
		if str(node.get_meta("extras",{}).get("source_name","")).begins_with("COMPLETE Building garden island"):bodies.append(node.mesh)
	if bodies.size()!=4:
		return "The imported terrain mesh is missing"
	var points: Array[Vector2] = [Vector2(-24.0,3.44), Vector2(-23.0,2.8), Vector2(-22.0,2.17), Vector2(-21.25,1.70)]
	for point: Vector2 in points:
		var material := material_at(bodies, point.x, point.y)
		if "lake" not in material or "garden" not in material:
			return "The imported flowerbed belt is broken at %s: %s" % [point, material]
	if "warm" not in material_at(bodies, -23.0, 4.6):
		return "The flowerbed extension changed the neighboring lawn"
	if "moss" not in material_at(bodies, -23.0, 1.5):
		return "The flowerbed extension changed the neighboring forest"
	return ""

func run() -> void:
	var scene := (load(GROUND) as PackedScene).instantiate() as Node3D
	var error := validate_library(scene)
	scene.free()
	if not error.is_empty():
		push_error(error)
		quit(1)
		return
	print("FLOWERBED_RING_JOIN_OK")
	quit(0)
