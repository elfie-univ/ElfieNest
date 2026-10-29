extends Node3D

## Read-only graphics from the loaded world's actual physics and navigation.
const LAYERS := preload("res://runtime/world/collision_layers.gd")
const LEGEND_FONT := preload("res://ui/fonts/NotoSansSC-OutdoorAccess.ttf")
const VIEW_IDS := ["access-estate", "access-forest"]
var _nest: ModularNest
var _graphics: Node3D
var _legend: Control
var _canopies: Dictionary = {}
var _obstacles: Array[Dictionary] = []
var _navigation: MeshInstance3D
var _boundary_triangles := 0
var _navigation_triangles := 0
var _built := false

func setup(nest: ModularNest) -> void:
	set_process(false)
	_nest = nest
	# Nest constructs its source estate in a deferred rebuild.
	if _nest.get_node_or_null("Generated") == null:
		await get_tree().process_frame
	_graphics = Node3D.new()
	_graphics.name = "ActualOutdoorPhysicsDisplay"
	add_child(_graphics)
	_graphics.visible = false
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(24,24)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.add_child(panel)
	var text := RichTextLabel.new()
	text.bbcode_enabled = true
	text.fit_content = true
	text.custom_minimum_size = Vector2(640,144)
	text.add_theme_font_size_override("normal_font_size",28)
	text.add_theme_font_override("normal_font",LEGEND_FONT)
	text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	text.text = "[color=#25ee8c]绿色：实际可走导航区域[/color]\n[color=#ff5353]红色：可走区域边界[/color]\n[color=#ffd44f]黄色：实体障碍碰撞[/color]\n当前隐藏树冠；切回普通机位恢复"
	panel.add_child(text)
	_legend = panel
	_legend.visible = false
	_nest.observer_camera_catalog_changed.connect(_on_selection)
	_nest.add_access_observer_views()
	set_process(false)

func _build() -> void:
	var estate := _nest.get_node("Generated/CompleteEstate") as Node3D
	var physics := _nest.get_node("Generated/EstatePhysics") as Node3D
	var contour := PackedVector3Array()
	for edge: Dictionary in physics.outdoor_access.boundary_segments:
		var a: Vector2 = edge["a"]
		var b: Vector2 = edge["b"]
		var middle := (a+b)*0.5
		var normal := (b-a).orthogonal().normalized()*0.08
		if not physics.outdoor_access.contains_outdoor_point(middle+normal) and not physics.outdoor_access.contains_outdoor_point(middle-normal): continue
		var steps := maxi(1,ceili(a.distance_to(b)))
		for j in range(steps):
			contour.append(_ground_contour_point(a.lerp(b,float(j)/steps)))
			contour.append(_ground_contour_point(a.lerp(b,float(j+1)/steps)))
	_boundary_triangles = physics.outdoor_access.boundary_segments.size()*2
	_mesh_visual("ActualOutdoorBoundaryContour",contour,Color(1,0.12,0.08),Mesh.PRIMITIVE_LINES,4)
	for owner: Node3D in [estate,physics]:
		for collision: CollisionShape3D in owner.find_children("*", "CollisionShape3D", true, false):
			var body := collision.get_parent() as CollisionObject3D
			if body == null or body.collision_layer & LAYERS.WORLD_SOLIDS == 0 or collision.shape == null: continue
			if not str(body.get_meta("estate_module", "")).is_empty(): continue
			if str(body.name) in ["GardenCollision_Terrain","GardenCollision_Boundary","GardenCollision_Hardscape"]: continue
			var visual := MeshInstance3D.new()
			visual.mesh = collision.shape.get_debug_mesh()
			visual.material_override = _material(Color(1,0.78,0.1,0.4),5)
			_graphics.add_child(visual)
			visual.global_transform = collision.global_transform
			_obstacles.append({"source":collision,"visual":visual})
	for node: Node3D in estate.find_children("*", "Node3D", true, false):
		var bounds := AABB()
		if node is MultiMeshInstance3D and node.multimesh != null:
			bounds = node.global_transform * node.multimesh.get_aabb()
		elif node is MeshInstance3D and node.mesh != null:
			if not str((node.get_meta("extras",{}) as Dictionary).get("module", "")).is_empty(): continue
			bounds = node.global_transform * node.get_aabb()
		else: continue
		if bounds.end.y > 3.0:
			_canopies[node] = node.visible
	_built = true

func _ground_contour_point(point: Vector2) -> Vector3:
	var ray := PhysicsRayQueryParameters3D.create(Vector3(point.x,1.4,point.y),Vector3(point.x,-1.5,point.y),LAYERS.WORLD_SOLIDS)
	var hit := get_world_3d().direct_space_state.intersect_ray(ray)
	var height := 0.1 if hit.is_empty() else (hit["position"] as Vector3).y
	return Vector3(point.x,height+0.04,point.y)

func _build_navigation() -> void:
	var region := _nest.get_node_or_null("RuntimeNavigation") as NavigationRegion3D
	if region == null or region.navigation_mesh == null: return
	var nav := region.navigation_mesh
	var vertices := nav.get_vertices()
	var faces := PackedVector3Array()
	for i in range(nav.get_polygon_count()):
		var polygon := nav.get_polygon(i)
		for j in range(1,polygon.size()-1):
			var triangle := PackedVector3Array([vertices[polygon[0]],vertices[polygon[j]],vertices[polygon[j+1]]])
			if maxf(triangle[0].y,maxf(triangle[1].y,triangle[2].y)) > 1.4: continue
			var middle := (triangle[0]+triangle[1]+triangle[2])/3.0
			var access: Node3D = _nest.get_node("Generated/EstatePhysics/OutdoorAccess")
			if not access.contains_outdoor_point(Vector2(middle.x,middle.z)): continue
			for vertex: Vector3 in triangle:
				faces.append(region.global_transform * vertex + Vector3.UP * 0.035)
	if faces.is_empty(): return
	_navigation_triangles = faces.size()/3
	_navigation = _mesh_visual("ActualGroundNavigation",faces,Color(0.03,0.94,0.44,0.65),Mesh.PRIMITIVE_TRIANGLES,3)

func _material(color: Color, priority: int) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = color
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.no_depth_test = true
	material.render_priority = priority
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return material

func _mesh_visual(label: String, vertices: PackedVector3Array, color: Color, primitive: Mesh.PrimitiveType, priority: int) -> MeshInstance3D:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(primitive,arrays)
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.mesh = mesh
	visual.material_override = _material(color,priority)
	visual.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_graphics.add_child(visual)
	visual.global_transform = Transform3D.IDENTITY
	return visual

func _on_selection(catalog: Dictionary) -> void:
	var enabled := str(catalog["active_id"]) in VIEW_IDS
	if enabled and not _built: _build()
	_graphics.visible = enabled
	_legend.visible = enabled
	for canopy: Node3D in _canopies:
		canopy.visible = false if enabled else bool(_canopies[canopy])
	set_process(enabled)
	if enabled: _process(0.0)

func _process(_delta: float) -> void:
	if _navigation == null: _build_navigation()
	for record: Dictionary in _obstacles:
		var source := record["source"] as CollisionShape3D
		var visual := record["visual"] as MeshInstance3D
		visual.global_transform = source.global_transform
		visual.visible = not source.disabled

func report() -> Dictionary:
	var hidden := 0
	for canopy: Node3D in _canopies:
		if bool(_canopies[canopy]) and not canopy.visible: hidden += 1
	return {"visible":_graphics.visible,"hidden_canopies":hidden,"boundary_triangles":_boundary_triangles,"navigation_triangles":_navigation_triangles,"obstacle_shapes":_obstacles.size()}

func _exit_tree() -> void:
	for canopy: Variant in _canopies:
		if is_instance_valid(canopy): canopy.visible = bool(_canopies[canopy])
