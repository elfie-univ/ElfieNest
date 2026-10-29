extends Node3D
## Partial geometry framing review using the unchanged production fixed catalog.
## The monolithic GLB still loads; landscape instances and world services do not.

const SOURCE := preload("res://rooms/estate/ElfieNest-complete-final.glb")
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const LIGHTING := preload("res://rooms/estate/estate_lighting.gd")
var camera_owner: ModularNest
var initial_view_id := "overview"
var review_geometry: Node3D
var _source: Node3D
var _meshes: Array[MeshInstance3D] = []
var _active: Array[MeshInstance3D] = []
var _sky: Array[MeshInstance3D] = []
var _active_id := ""
var _face_reference: ElfieActor
var _faces_enabled := false


static func is_requested() -> bool:
	return OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('catalog')")) == "fixed"


func _ready() -> void:
	build()


func build() -> void:
	review_geometry = Node3D.new()
	review_geometry.name = "SelectedActualCameraGeometry"
	add_child(review_geometry)
	_source = SOURCE.instantiate() as Node3D
	_source.name = "HiddenOriginalGeometry"
	_source.visible = false
	add_child(_source)
	# Imported physical bodies are not part of this framing-only review.
	# Retain any visual children in world coordinates before removing a body.
	for body: CollisionObject3D in _source.find_children("*", "CollisionObject3D", true, false):
		for child: Node in body.get_children():
			if child is Node3D and not child is CollisionShape3D and not child is CollisionPolygon3D:
				child.reparent(_source, true)
		body.free()
	DAYLIGHT.apply(_source)
	var ordinary := LIGHTING.new()
	ordinary.bind(_source)
	ordinary.apply(false)
	for mesh: MeshInstance3D in _source.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or _is_template(mesh):
			continue
		_meshes.append(mesh)
		for surface in range(mesh.mesh.get_surface_count()):
			var material := mesh.get_active_material(surface)
			if material != null and DAYLIGHT._is_background(material.resource_name.to_lower()):
				_sky.append(mesh)
				break
	# Keep source daylight inputs, including their original per-room masks.
	# Only selected geometry renders; the source hierarchy itself stays hidden.
	var lights := Node3D.new()
	lights.name = "SourceDaylight"
	add_child(lights)
	for light: Light3D in _source.find_children("*", "Light3D", true, false):
		light.reparent(lights, true)
	var reference := (load("res://rooms/nest.tscn") as PackedScene).instantiate()
	var environment := reference.get_node("WorldEnvironment") as WorldEnvironment
	reference.remove_child(environment)
	reference.free()
	add_child(environment)
	var cameras := Node3D.new()
	cameras.name = "UnchangedProductFixedCameras"
	camera_owner.add_child(cameras)
	camera_owner._camera_views.clear()
	camera_owner._build_observation_views(cameras, _source)
	var hud := camera_owner.get_node("ObservationHUD") as ObservationHUD
	var selected := Callable(camera_owner, "select_observation_view")
	if not hud.is_connected("view_selected", selected):
		hud.connect("view_selected", selected)
	camera_owner.observer_camera_catalog_changed.connect(_on_selection)
	if OS.has_feature("web"):
		initial_view_id = str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('view')||'overview'"))
		_faces_enabled = str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('faces')||''"))=="1"
	if not camera_owner.select_observer_camera_by_id(initial_view_id):
		push_error("Unknown fixed review camera: " + initial_view_id)
		return
	_on_selection(camera_owner.observer_camera_catalog())


func _on_selection(catalog: Dictionary) -> void:
	var id := str(catalog.get("active_id", ""))
	if id == _active_id:
		return
	_active_id = id
	for mesh: MeshInstance3D in _active:
		mesh.reparent(_source, true)
	_active.clear()
	for mesh: MeshInstance3D in _meshes:
		if _selected(mesh, id):
			mesh.reparent(review_geometry, true)
			mesh.visible = true
			_active.append(mesh)
	var active: Dictionary = camera_owner._camera_views[camera_owner.observation_active_view_index()]
	var camera := active["camera"] as Camera3D
	_show_face_reference(id,camera)
	print("ESTATE_FIXED_CAMERA_REVIEW ", JSON.stringify({"id": id, "meshes": _active.size(), "position": _coordinates(camera.global_position), "target": _coordinates(active["target"]), "fov": camera.fov, "catalog_count": camera_owner.observation_view_count(), "landscape_instances": false, "scope": "Partial geometry composition only; full GLB download unchanged; no whole-estate occlusion or rendering acceptance"}))


func _show_face_reference(id: String,camera: Camera3D) -> void:
	if not _faces_enabled: return
	if _face_reference!=null: _face_reference.visible=false
	if not (id.begins_with("dorm-") or id.begins_with("terrace-")): return
	var module_name := "M"+id.get_slice("-",1)
	var lower := id.begins_with("dorm-")
	var floor_mesh: MeshInstance3D
	for mesh: MeshInstance3D in _meshes:
		var e := mesh.get_meta("extras",{}) as Dictionary
		var source := str(e.get("source_name",""))
		if e.get("module")==module_name and ((lower and source.contains("continuous lower floor")) or (not lower and source.contains("inset terrace walking finish"))): floor_mesh=mesh
	if floor_mesh==null: return
	var bounds := floor_mesh.get_aabb()
	var point := Vector3(0,bounds.end.y+0.02,-0.3 if lower else bounds.get_center().z-0.6)
	if _face_reference==null:
		_face_reference=load("res://characters/tovren/tovren.tscn").instantiate() as ElfieActor
		_face_reference.name="LocalCameraFaceReference"
		_face_reference.set_meta("local_visual_sample",true)
		add_child(_face_reference)
		_face_reference.configure("local-camera-face-reference",floor_mesh.to_global(point))
		_face_reference.set_physics_process(false)
		(_face_reference.get_node("NavigationAgent3D") as NavigationAgent3D).avoidance_enabled=false
		_face_reference.remove_from_group(&"runtime_elfie_actors")
	_face_reference.global_position=floor_mesh.to_global(point)
	var facing := camera.global_position
	facing.y=_face_reference.global_position.y
	_face_reference.look_at(facing,Vector3.UP,true)
	_face_reference.visible=true


func _selected(mesh: MeshInstance3D, id: String) -> bool:
	var extras := mesh.get_meta("extras", {}) as Dictionary
	var module := str(extras.get("module", ""))
	if id == "overview":
		return module.is_empty() or not bool(extras.get("furniture", false))
	if module.is_empty():
		return _sky.has(mesh)
	if id.begins_with("central-"):
		# Full-height envelope, all slabs and skylight remain real occluders.
		return module == "central" and (not bool(extras.get("furniture", false)) or int(extras.get("floor", 1)) == int(id.get_slice("-", 1)))
	if id.begins_with("dorm-") or id.begins_with("terrace-"):
		# Both levels of the selected cabin stay intact: no ceiling cutaway.
		return module == "M" + id.get_slice("-", 1)
	return false


static func _is_template(mesh: Node) -> bool:
	var node := mesh
	while node != null:
		if str(node.name).begins_with("__ELFIE_INST_GROUP_"):
			return true
		node = node.get_parent()
	return false


static func _coordinates(point: Vector3) -> Array[float]:
	return [point.x, point.y, point.z]
