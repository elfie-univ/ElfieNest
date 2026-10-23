extends SceneTree
## Run with the repository Godot toolchain after importing the estate once.

const WATER_PATH := "res://rooms/estate/estate_water.gd"


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	if not _require(ResourceLoader.exists(WATER_PATH), "Estate water attach implementation is missing"):
		return
	var water = load(WATER_PATH)
	var fixture := Node3D.new()
	root.add_child(fixture)
	var marker := Node3D.new()
	marker.set_meta("extras", {"sourceGardenNode": 258})
	fixture.add_child(marker)
	var original := StandardMaterial3D.new()
	original.albedo_color = Color(0.32, 0.48, 0.49, 1.0)
	original.roughness = 0.22
	original.metallic = 0.02
	original.set_meta("source_optics", {"clearcoat": 0.65, "clearcoat_roughness": 0.2})
	var lake := MeshInstance3D.new()
	lake.name = "COMPLETE Inset natural lake"
	lake.mesh = PlaneMesh.new()
	lake.mesh.material = original
	lake.position = Vector3(2, 3, 4)
	fixture.add_child(lake)
	var saved_mesh := lake.mesh
	var saved_transform := lake.transform
	# Match the real integration order, including daylight's source wrapper.
	var surface := load("res://rooms/estate/estate_surface.gd")
	lake.set_surface_override_material(0, surface.make_material(original, 0.65, 0.2))
	fixture.visible = false
	var counts: Dictionary = water.attach(fixture)
	var animated := lake.get_active_material(0) as ShaderMaterial
	if not _require(counts["surface"] == 1 and animated != null, "Hidden-at-attach water cannot later animate"):
		return
	if not _require(animated.get_shader_parameter("source_albedo") == original.albedo_color and animated.get_shader_parameter("source_roughness") == original.roughness and animated.get_shader_parameter("source_metallic") == original.metallic, "Water lost source color or physical material inputs"):
		return
	if not _require(lake.mesh == saved_mesh and lake.transform == saved_transform and lake.mesh.surface_get_material(0) == original, "Animation changed geometry, transform or imported material"):
		return
	fixture.visible = true
	water.attach(fixture)
	if not _require(lake.get_active_material(0) == animated and lake.is_visible_in_tree(), "Attach is not idempotent or prevents later visibility"):
		return
	fixture.free()
	# Load only the imported model, avoiding physics, navigation and sidecar restore.
	var estate := (load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene).instantiate() as Node3D
	root.add_child(estate)
	var daylight := load("res://rooms/estate/estate_daylight.gd")
	daylight.apply(estate)
	var meshes: Dictionary = {}
	var transforms: Dictionary = {}
	var previous: Dictionary = {}
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		meshes[mesh] = mesh.mesh
		transforms[mesh] = mesh.transform
		previous[mesh] = mesh.get_active_material(0)
	counts = water.attach(estate)
	if not _require(counts == {"surface": 3, "spillway": 2, "jet": 11, "ripple": 9, "foam": 1}, "Actual source water inventory changed: " + str(counts)):
		return
	var changed := 0
	for mesh: MeshInstance3D in meshes:
		if not _require(mesh.mesh == meshes[mesh] and mesh.transform == transforms[mesh], "Source mesh or transform changed"):
			return
		if mesh.get_active_material(0) == previous[mesh]:
			continue
		changed += 1
		var material := mesh.get_active_material(0) as ShaderMaterial
		if not _require(material != null and not material.shader.get_shader_uniform_list().is_empty(), "Water shader failed to compile"):
			return
		var source := mesh.mesh.surface_get_material(0) as BaseMaterial3D
		if not _require(material.get_shader_parameter("source_albedo") == source.albedo_color and material.get_shader_parameter("source_roughness") == source.roughness, "Actual source water appearance inputs changed"):
			return
	if not _require(changed == 26, "Unexpected non-water material changes"):
		return
	water.attach(estate)
	estate.free()
	print("PASS: 26 metadata-bound water surfaces; source geometry/color retained; hidden attach and repeat attach supported")
	quit(0)


func _require(condition: bool, message: String) -> bool:
	if not condition:
		push_error(message)
		quit(1)
	return condition
