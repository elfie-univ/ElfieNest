extends SceneTree

const SCENE_PATH := "res://rooms/estate/estate.tscn"
const PLACEMENTS_PATH := "res://rooms/estate/placements.json"


func _init() -> void:
	call_deferred("_validate")


func _validate() -> void:
	for model: String in ["central.glb", "pod.glb"]:
		for dependency: String in ResourceLoader.get_dependencies("res://rooms/estate/" + model):
			if ".png" in dependency:
				_fail("Imported models must retain embedded textures without extracted PNG dependencies")
				return
	var layout = JSON.parse_string(FileAccess.get_file_as_string(PLACEMENTS_PATH))
	if not layout is Dictionary or layout.get("pods", []).size() != 8:
		_fail("Expected eight recorded house placements")
		return
	var resource := load(SCENE_PATH) as PackedScene
	if resource == null:
		_fail("Estate visual baseline could not be loaded")
		return
	var estate := resource.instantiate() as Node3D
	if estate == null or estate.get_child_count() != 9:
		_fail("Expected one central building and eight independent house roots")
		return
	if estate.get_node_or_null("Central") == null:
		estate.free()
		_fail("Central building missing")
		return
	var shared_mesh: Mesh = null
	for placement: Dictionary in layout["pods"]:
		var house := estate.get_node_or_null(placement["id"]) as Node3D
		if house == null or house.get_meta("module", "") != placement["id"]:
			estate.free()
			_fail("House instance identity missing")
			return
		var matrix: Array = placement["matrix"]
		var expected := Transform3D(
			Vector3(matrix[0], matrix[1], matrix[2]),
			Vector3(matrix[4], matrix[5], matrix[6]),
			Vector3(matrix[8], matrix[9], matrix[10]),
			Vector3(matrix[12], matrix[13], matrix[14])
		)
		if not house.transform.is_equal_approx(expected):
			push_error("%s actual=%s expected=%s" % [placement["id"], house.transform, expected])
			estate.free()
			_fail("House placement changed")
			return
		var mesh := _first_mesh(house)
		if mesh == null or (shared_mesh != null and shared_mesh != mesh):
			estate.free()
			_fail("House instances must share the same imported mesh resource")
			return
		shared_mesh = mesh
	print("Estate asset baseline passed: central + 8 independent houses; shared mesh; original placements")
	estate.free()
	quit(0)


func _first_mesh(node: Node) -> Mesh:
	if node is MeshInstance3D:
		return (node as MeshInstance3D).mesh
	for child: Node in node.get_children():
		var found := _first_mesh(child)
		if found != null:
			return found
	return null


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
