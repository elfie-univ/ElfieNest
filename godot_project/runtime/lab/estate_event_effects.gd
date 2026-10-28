extends Node3D
## Local visual candidates only. No resident state, event receipt or authority.

const COVER_SHADER := preload("res://runtime/lab/estate_cover.gdshader")

var _bed: Node3D
var _arrival: Node3D
var _dome: MeshInstance3D
var _indicator: MeshInstance3D
var _bed_light: OmniLight3D
var _ring: MeshInstance3D
var _beam: MeshInstance3D
var cover_phase := "idle"
var arrival_phase := "idle"


func configure_bed(frame: Transform3D, bounds: AABB, shell_points: PackedVector3Array = PackedVector3Array(), crown_points: PackedVector3Array = PackedVector3Array()) -> void:
	if is_instance_valid(_bed):
		_bed.free()
	_bed = Node3D.new()
	_bed.name = "BedEffect"
	add_child(_bed)
	_bed.global_transform = frame
	var center := bounds.get_center()
	# Use the authored bed's long axis in its own frame. The capsule radius
	# follows the full shell width; its straight section encloses real shell
	# vertices, including the broad rounded ends, rather than the duvet AABB.
	var radius := maxf(bounds.size.x * 0.5, 0.05) + 0.015
	var half_straight := maxf(bounds.size.z * 0.5 - radius, 0.0)
	for point: Vector3 in shell_points:
		var across := point.x - center.x
		var end_reach := sqrt(maxf(radius * radius - across * across, 0.0))
		half_straight = maxf(half_straight, absf(point.z - center.z) - end_reach)
	var canopy := _half_capsule(radius, half_straight, center, bounds.end.y, crown_points) if crown_points.is_empty() else _fitted_crown_cover(center, crown_points)
	_dome = _mesh(_bed, "GlassDome", canopy, Color(0.08, 0.46, 0.64))
	_dome.position = Vector3(center.x, 0.0, center.z)
	# A bounded view-dependent tint makes the existing curved surface readable
	# without a separate top ring or dimming the sleeping body through dark glass.
	var glass := ShaderMaterial.new()
	glass.shader = COVER_SHADER
	glass.set_shader_parameter("cover_tint", Color(0.10, 0.56, 0.76))
	glass.set_shader_parameter("face_opacity", 0.28)
	glass.set_shader_parameter("edge_opacity", 0.48)
	glass.set_shader_parameter("face_glow", 0.08)
	glass.set_shader_parameter("edge_glow", 0.24)
	_dome.material_override = glass
	var bulb := SphereMesh.new()
	bulb.radius = 0.018
	bulb.height = 0.036
	_indicator = _mesh(_bed, "BedsideIndicator", bulb, Color(0.28, 0.80, 0.65))
	_indicator.position = Vector3(bounds.end.x, bounds.end.y + 0.018, center.z)
	if not crown_points.is_empty():
		var nearest := INF
		for vertex: Vector3 in crown_points:
			var distance := Vector2(vertex.x, vertex.z).distance_squared_to(Vector2(bounds.end.x, center.z))
			if distance < nearest:
				nearest = distance
				_indicator.position = vertex + Vector3.UP * 0.018
	_bed_light = OmniLight3D.new()
	_bed_light.name = "BedsideIndicatorLight"
	_bed_light.light_color = Color(0.28, 0.80, 0.65)
	_bed_light.omni_range = 0.18
	_bed_light.shadow_enabled = false
	_bed.add_child(_bed_light)
	_bed_light.position = _indicator.position
	preview_cover(0.0)


static func _half_capsule(radius: float, half_straight: float, center: Vector3, fallback_edge: float, crown_points: PackedVector3Array) -> ArrayMesh:
	var rings: Array[Vector2] = []
	# Each ring stores source-Z and its upper semicircle radius. Straight
	# rings keep a circular cross section; end rings shrink on a sphere.
	for step in range(13):
		var angle := (1.0 - float(step) / 12.0) * PI * 0.5
		rings.append(Vector2(-half_straight - radius * sin(angle), radius * cos(angle)))
	for step in range(1, 9):
		rings.append(Vector2(lerpf(-half_straight, half_straight, float(step) / 8.0), radius))
	for step in range(1, 13):
		var angle := float(step) / 12.0 * PI * 0.5
		rings.append(Vector2(half_straight + radius * sin(angle), radius * cos(angle)))
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var indices := PackedInt32Array()
	const SIDES := 32
	for ring: Vector2 in rings:
		var axial := ring.x - clampf(ring.x, -half_straight, half_straight)
		var right_edge := _crown_height(Vector2(center.x + ring.y, center.z + ring.x), crown_points, fallback_edge)
		var left_edge := _crown_height(Vector2(center.x - ring.y, center.z + ring.x), crown_points, fallback_edge)
		for side in range(SIDES + 1):
			var angle := float(side) / float(SIDES) * PI
			var edge := lerpf(right_edge, left_edge, (1.0 - cos(angle)) * 0.5) + 0.01
			var point := Vector3(ring.y * cos(angle), edge + ring.y * sin(angle), ring.x)
			vertices.append(point)
			normals.append(Vector3(point.x, ring.y * sin(angle), axial).normalized())
	for ring_index in range(rings.size() - 1):
		for side in range(SIDES):
			var first := ring_index * (SIDES + 1) + side
			var next := first + SIDES + 1
			indices.append_array(PackedInt32Array([first, next, first + 1, first + 1, next, next + 1]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var result := ArrayMesh.new()
	result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return result


static func _fitted_crown_cover(center: Vector3, crown_points: PackedVector3Array) -> ArrayMesh:
	var projection := PackedVector2Array()
	for point: Vector3 in crown_points:
		projection.append(Vector2(point.x, point.z))
	# The authored crown is a closed, nearly convex rounded contour. Its real
	# outline preserves the long wall-side barrel and rounded head/foot without
	# expanding a mathematical capsule to fit the shell's rectangular bounds.
	var contour := Geometry2D.convex_hull(projection)
	var outlines := Geometry2D.offset_polygon(contour, 0.01)
	if not outlines.is_empty():
		contour = outlines[0]
	var min_z := INF
	var max_z := -INF
	for point: Vector2 in contour:
		min_z = minf(min_z, point.y)
		max_z = maxf(max_z, point.y)
	var rings: Array[Vector3] = []
	for step in range(97):
		var z := lerpf(min_z, max_z, float(step) / 96.0)
		var crossings: Array[float] = []
		for index in range(contour.size()):
			var first := contour[index]
			var next := contour[(index + 1) % contour.size()]
			if z < minf(first.y, next.y) - 0.00001 or z > maxf(first.y, next.y) + 0.00001:
				continue
			if absf(next.y - first.y) < 0.00001:
				crossings.append(first.x)
				crossings.append(next.x)
			else:
				crossings.append(lerpf(first.x, next.x, clampf((z - first.y) / (next.y - first.y), 0.0, 1.0)))
		if crossings.is_empty():
			continue
		crossings.sort()
		rings.append(Vector3(z, crossings[0], crossings[-1]))
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var indices := PackedInt32Array()
	const SIDES := 32
	for ring: Vector3 in rings:
		var radius := (ring.z - ring.y) * 0.5
		var middle := (ring.z + ring.y) * 0.5
		var right_edge := _crown_height(Vector2(ring.z, ring.x), crown_points, center.y)
		var left_edge := _crown_height(Vector2(ring.y, ring.x), crown_points, center.y)
		for side in range(SIDES + 1):
			var angle := float(side) / float(SIDES) * PI
			var edge := lerpf(right_edge, left_edge, (1.0 - cos(angle)) * 0.5) + 0.01
			vertices.append(Vector3(middle - center.x + radius * cos(angle), edge + radius * sin(angle), ring.x - center.z))
	for ring_index in range(rings.size() - 1):
		for side in range(SIDES):
			var first := ring_index * (SIDES + 1) + side
			var next := first + SIDES + 1
			indices.append_array(PackedInt32Array([first, next, first + 1, first + 1, next, next + 1]))
	# Fit normals to the real rounded ends and varying source crown height.
	normals.resize(vertices.size())
	for triangle in range(0, indices.size(), 3):
		var first := indices[triangle]
		var second := indices[triangle + 1]
		var third := indices[triangle + 2]
		var normal := (vertices[third] - vertices[first]).cross(vertices[second] - vertices[first])
		normals[first] += normal
		normals[second] += normal
		normals[third] += normal
	for index in range(normals.size()):
		normals[index] = normals[index].normalized() if normals[index].length_squared() > 0.0 else Vector3.UP
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var result := ArrayMesh.new()
	result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return result


static func _crown_height(point: Vector2, crown_points: PackedVector3Array, fallback: float) -> float:
	var nearest := INF
	var height := fallback
	for vertex: Vector3 in crown_points:
		var distance := point.distance_squared_to(Vector2(vertex.x, vertex.z))
		if distance < nearest:
			nearest = distance
			height = vertex.y
	return height


func configure_arrival(anchor_position: Vector3, radius: float) -> void:
	if is_instance_valid(_arrival):
		_arrival.free()
	_arrival = Node3D.new()
	_arrival.name = "ArrivalEffect"
	add_child(_arrival)
	_arrival.global_position = anchor_position
	_ring = _mesh(_arrival, "ArrivalRing", _torus(), Color(0.40, 0.82, 1.0))
	_ring.position.y = 0.045
	_ring.scale = Vector3(radius, 0.05, radius)
	var column := CylinderMesh.new()
	column.top_radius = radius * 0.45
	column.bottom_radius = radius * 0.45
	column.height = 2.3
	column.cap_top = false
	column.cap_bottom = false
	_beam = _mesh(_arrival, "ArrivalBeam", column, Color(0.48, 0.86, 1.0))
	_beam.position.y = 1.15
	preview_arrival(0.0)


func preview_cover(seconds: float) -> void:
	if not is_instance_valid(_bed):
		return
	var level := 0.0
	cover_phase = "idle"
	if seconds > 0.0 and seconds < 1.0:
		level = smoothstep(0.0, 1.0, seconds)
		cover_phase = "fade_in"
	elif seconds >= 1.0 and seconds < 4.0:
		level = 1.0
		cover_phase = "hold"
	elif seconds >= 4.0 and seconds < 5.0:
		level = 1.0 - smoothstep(4.0, 5.0, seconds)
		cover_phase = "fade_out"
	_level(_dome, level, 0.48, 0.18)
	var pulse := 0.5-0.5*cos(TAU*(seconds-1.0)/3.2) if level>0.0 else 0.0
	(_dome.material_override as ShaderMaterial).set_shader_parameter("edge_pulse",pulse)
	_level(_indicator, level, 0.65, 0.12)
	_bed_light.visible = level > 0.001
	_bed_light.light_energy = 0.015 * level


func preview_arrival(seconds: float) -> void:
	if not is_instance_valid(_arrival):
		return
	var ring_level := 0.0
	var beam_level := 0.0
	arrival_phase = "idle"
	if seconds > 0.0 and seconds < 1.0:
		ring_level = smoothstep(0.0, 1.0, seconds)
		arrival_phase = "warmup"
	elif seconds >= 1.0 and seconds < 2.5:
		ring_level = 1.0
		beam_level = 1.0
		arrival_phase = "arrival_candidate"
	elif seconds >= 2.5 and seconds < 4.0:
		ring_level = 1.0 - smoothstep(2.5, 4.0, seconds)
		beam_level = ring_level
		arrival_phase = "dissipating"
	_level(_ring, ring_level, 0.7, 1.4)
	_level(_beam, beam_level, 0.14, 0.55)


func cancel_preview() -> void:
	preview_cover(6.0)
	preview_arrival(6.0)


static func _torus() -> TorusMesh:
	var mesh := TorusMesh.new()
	mesh.inner_radius = 0.97
	mesh.outer_radius = 1.0
	return mesh


static func _mesh(parent: Node3D, label: String, mesh: Mesh, tint: Color) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = label
	node.mesh = mesh
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(tint, 0.0)
	material.roughness = 0.12
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.emission_enabled = true
	material.emission = tint
	material.emission_energy_multiplier = 0.0
	node.material_override = material
	parent.add_child(node)
	return node


static func _level(mesh: MeshInstance3D, level: float, alpha: float, emission: float) -> void:
	mesh.visible = level > 0.001
	if mesh.material_override is ShaderMaterial:
		(mesh.material_override as ShaderMaterial).set_shader_parameter("cover_level", level)
		return
	var material := mesh.material_override as StandardMaterial3D
	material.albedo_color.a = alpha * level
	material.emission_energy_multiplier = emission * level
