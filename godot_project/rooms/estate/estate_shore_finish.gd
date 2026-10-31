extends RefCounted
## Follow the real bank geometry; keep land foliage clear of the water edge.

var water := PackedVector2Array()
var water_bounds := Rect2()
var water_height := 0.0
var bank_top := 0.0
var bank_bottom := 0.0

func apply(estate: Node3D, layout: Node3D) -> void:
	var old_rim := layout.find_child("WholeLakeConcealedRim", true, false) as MeshInstance3D
	if old_rim != null: old_rim.hide()
	var outline: PackedVector3Array = layout.get_meta("shoreline")
	for i in range(outline.size() - 1): water.append(Vector2(outline[i].x, outline[i].z))
	water_bounds = Rect2(water[0], Vector2.ZERO)
	for point: Vector2 in water: water_bounds = water_bounds.expand(point)
	var lake := estate.find_child("COMPLETE Inset natural lake", true, false) as MeshInstance3D
	water_height = (lake.global_transform * lake.get_aabb()).end.y
	var bank := estate.find_child("CY R003 corrected CY R002 continuous natural shore slope 0", true, false) as MeshInstance3D
	bank_top = (bank.global_transform * bank.get_aabb()).end.y
	bank_bottom = (bank.global_transform * bank.get_aabb()).position.y
	var image := Image.create(16, 64, false, Image.FORMAT_RGB8)
	for y in range(64):
		for x in range(16):
			var level := lerpf(bank_bottom, bank_top, float(y) / 63.0)
			var height := clampf((level - water_height) / (bank_top - water_height), 0.0, 1.0)
			var strength := float(x) / 15.0 * pow(height, 1.5)
			image.set_pixel(x, y, Color(strength, strength, strength).linear_to_srgb())
	image.generate_mipmaps()
	var mask := ImageTexture.create_from_image(image)
	for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
		var label := str(mesh.name)
		if not label.begins_with("CY R003 corrected CY R002 continuous natural shore slope") and label not in ["CY R003 corrected CY R002 lakeside returned solid planting bank", "CY R003 corrected CY R002 lakeside gently sloping planted shore", "CY R003 corrected CY SHORE solid Continuous planted lake bank", "CY R003 corrected CY SHORE solid Lake sloping bank", "CY R003 circular waterfront platform closed foundation"]: continue
		var finished := ArrayMesh.new()
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface).duplicate(true)
			# Shared rim vertices can carry upward normals from the platform top.
			# Split indexed faces so the vertical fascia keeps its own light mask.
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if not indices.is_empty():
				for attribute in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_COLOR]:
					if arrays[attribute] == null: continue
					var source = arrays[attribute]
					var expanded = source.duplicate()
					expanded.resize(indices.size())
					for index in range(indices.size()): expanded[index] = source[indices[index]]
					arrays[attribute] = expanded
				arrays[Mesh.ARRAY_INDEX] = null
				arrays[Mesh.ARRAY_TANGENT] = null
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var uv := PackedVector2Array()
			for i in range(points.size()):
				var point := mesh.global_transform * points[i]
				var triangle := i - i % 3
				var face := (points[triangle + 1] - points[triangle]).cross(points[triangle + 2] - points[triangle]).normalized()
				var facing := 1.0 - smoothstep(0.95, 0.999, absf(face.y))
				var coverage := facing
				var height := clampf((point.y - bank_bottom) / (bank_top - bank_bottom), 0.0, 1.0)
				uv.append(Vector2((coverage * 15.0 + 0.5) / 16.0, (height * 63.0 + 0.5) / 64.0))
			arrays[Mesh.ARRAY_TEX_UV2] = uv
			finished.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
			var original := mesh.get_active_material(surface) as BaseMaterial3D
			finished.surface_set_material(surface, mesh.mesh.surface_get_material(surface))
			var material := original.duplicate() as BaseMaterial3D
			material.resource_name = "Outdoor shoreline concealed warm wash lamp"
			material.emission_enabled = true
			material.emission = Color(1.0, 0.77, 0.44)
			material.emission_energy_multiplier = 1.1
			material.emission_operator = BaseMaterial3D.EMISSION_OP_MULTIPLY
			material.emission_on_uv2 = true
			material.emission_texture = mask
			mesh.set_surface_override_material(surface, material)
		mesh.mesh = finished
		var extras: Dictionary = mesh.get_meta("extras", {}).duplicate()
		extras["outdoor_fixture_id"] = "shoreline-wash"
		mesh.set_meta("extras", extras)

func nearest_edge(point: Vector2) -> Vector2:
	var nearest := water[0]
	var best := INF
	for i in range(water.size()):
		var candidate := Geometry2D.get_closest_point_to_segment(point, water[i], water[(i + 1) % water.size()])
		var distance := candidate.distance_squared_to(point)
		if distance < best:
			best = distance
			nearest = candidate
	return nearest

func retreat_plants(mesh: Mesh, buffer: PackedFloat32Array) -> int:
	var selected := false
	for surface in range(mesh.get_surface_count()):
		var material := mesh.surface_get_material(surface)
		if material != null and str(material.resource_name).begins_with("Layered low groundcover"): selected = true
	if not selected: return 0
	var moved := 0
	var bounds := mesh.get_aabb()
	for index in range(buffer.size() / 12):
		var offset := index * 12
		var root := Vector2(buffer[offset + 3], buffer[offset + 11])
		if not water_bounds.grow(2.0).has_point(root): continue
		var radius := 0.0
		for corner in range(8):
			var local := bounds.get_endpoint(corner)
			var delta := Vector2(buffer[offset] * local.x + buffer[offset + 1] * local.y + buffer[offset + 2] * local.z, buffer[offset + 8] * local.x + buffer[offset + 9] * local.y + buffer[offset + 10] * local.z)
			radius = maxf(radius, delta.length())
		var destination := root
		for attempt in range(6):
			var nearest := nearest_edge(destination)
			var inside := Geometry2D.is_point_in_polygon(destination, water)
			if not inside and destination.distance_to(nearest) >= radius + 0.55: break
			var outward := (destination - nearest).normalized()
			if inside: outward = -outward
			if outward.is_zero_approx(): outward = (nearest - water_bounds.get_center()).normalized()
			destination = nearest + outward * (radius + 0.56)
		if destination.distance_to(root) < 0.001: continue
		buffer[offset + 3] = destination.x
		buffer[offset + 11] = destination.y
		moved += 1
	return moved
