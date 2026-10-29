extends RefCounted
## Authoring only: retain source triangles/attributes while localizing light bounds.

static func partition(source: MeshInstance3D, parent: Node3D, cell_size: float = 8.0) -> Array[String]:
	var names: Array[String] = []
	for surface in range(source.mesh.get_surface_count()):
		var arrays := source.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
		var cells: Dictionary = {}
		var count := vertices.size() if indices.is_empty() else indices.size()
		for i in range(0, count, 3):
			var triangle := PackedInt32Array()
			var center := Vector3.ZERO
			for j in range(3):
				var index := i+j if indices.is_empty() else indices[i+j]
				triangle.append(index)
				center += source.global_transform * vertices[index] / 3.0
			var cell := Vector2i(floori(center.x/cell_size), floori(center.z/cell_size))
			if not cells.has(cell): cells[cell] = PackedInt32Array()
			var bucket: PackedInt32Array = cells[cell]
			bucket.append_array(triangle)
			cells[cell] = bucket
		for cell: Vector2i in cells:
			var selected := PackedInt32Array()
			var mapping: Dictionary = {}
			var remapped := PackedInt32Array()
			for old: int in cells[cell]:
				if not mapping.has(old):
					mapping[old] = selected.size()
					selected.append(old)
				remapped.append(mapping[old])
			var mesh := _packed_subset(source.mesh, surface, selected, remapped, vertices)
			mesh.surface_set_material(0, source.get_active_material(surface))
			var node := MeshInstance3D.new()
			node.name = "GroundPatch_%d" % parent.get_child_count()
			node.mesh = mesh
			node.set_meta("extras", {"lighting_ground_patch": true})
			node.set_meta("source_ground", str(source.name))
			node.set_meta("source_surface", surface)
			node.set_meta("source_indices", cells[cell])
			parent.add_child(node)
			node.global_transform = source.global_transform
			names.append(str(node.name))
	return names

static func strip(parent: Node3D, points: PackedVector3Array, width: float, label: String) -> MeshInstance3D:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var indices := PackedInt32Array()
	for i in range(points.size()-1):
		var a := points[i]
		var b := points[i+1]
		var normal := Vector3(-(b-a).z, 0, (b-a).x).normalized()*width*0.5
		var start := vertices.size()
		vertices.append_array(PackedVector3Array([a-normal, a+normal, b+normal, b-normal]))
		for j in range(4): normals.append(Vector3.UP)
		indices.append_array(PackedInt32Array([start, start+1, start+2, start, start+2, start+3]))
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var node := MeshInstance3D.new()
	node.name = label
	node.mesh = mesh
	var material := StandardMaterial3D.new()
	material.resource_name = "Outdoor concealed warm rim lamp"
	material.albedo_color = Color(0.68, 0.57, 0.38)
	material.emission_enabled = true
	material.emission = Color(1.0, 0.77, 0.44)
	material.emission_energy_multiplier = 1.1
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh.surface_set_material(0, material)
	node.set_meta("extras", {"lighting_diffuser": true})
	parent.add_child(node)
	return node

static func contour(mesh: MeshInstance3D) -> PackedVector3Array:
	var reader := preload("res://rooms/estate/estate_outdoor_access.gd").new()
	var loops: Array[PackedVector2Array] = reader._top_outlines(mesh, 0, -1.0)
	reader.free()
	assert(not loops.is_empty(), "Actual water boundary missing")
	var largest := loops[0]
	for loop: PackedVector2Array in loops:
		if absf(area(loop)) > absf(area(largest)): largest = loop
	var points := PackedVector3Array()
	var y := (mesh.global_transform*mesh.get_aabb()).end.y+0.025
	for point in largest: points.append(Vector3(point.x, y, point.y))
	points.append(points[0])
	return points

static func area(points: PackedVector2Array) -> float:
	var total := 0.0
	for i in range(points.size()): total += points[i].cross(points[(i+1)%points.size()])
	return total*0.5

static func shoreline_rim(water: PackedVector2Array, height: float) -> PackedVector3Array:
	# Keep the full 8 cm guidance strip on the bank side of the water boundary.
	var outlines := Geometry2D.offset_polygon(water, 0.08)
	assert(outlines.size() == 1, "Lake bank guidance must retain one closed outline")
	var points := PackedVector3Array()
	for point: Vector2 in outlines[0]:
		assert(not Geometry2D.is_point_in_polygon(point, water), "Lake bank guidance entered the water")
		points.append(Vector3(point.x, height, point.y))
	points.append(points[0])
	return points

static func round_local_rim(points: PackedVector3Array, centers: Array[Vector3]) -> PackedVector3Array:
	var sampled := PackedVector3Array()
	for i in range(points.size()-1):
		var local := false
		for center in centers:
			if Geometry3D.get_closest_point_to_segment(center,points[i],points[i+1]).distance_to(center)<0.9: local=true
		var count := maxi(1,ceili(points[i].distance_to(points[i+1])/0.04)) if local else 1
		for j in range(count):
			var point := points[i].lerp(points[i+1],float(j)/count)
			if not local or sampled.is_empty() or sampled[-1].distance_to(point)>0.001: sampled.append(point)
	var original := sampled.duplicate()
	for pass_index in range(3):
		var next := sampled.duplicate()
		for i in range(sampled.size()):
			var distance := INF
			for center in centers: distance=minf(distance,original[i].distance_to(center))
			if distance>=0.7: continue
			var average := sampled[i]*3.0
			for offset: float in [-0.3,-0.15,0.15,0.3]: average+=_point_along_loop(sampled,i,offset)
			var rounded := sampled[i].lerp(average/7.0,1.0-smoothstep(0.35,0.7,distance))
			next[i]=rounded
		sampled=next
	var cleaned := PackedVector3Array()
	for point in sampled:
		var local := false
		for center in centers:
			if point.distance_to(center)<0.8: local=true
		if local and not cleaned.is_empty() and point.distance_to(cleaned[-1])<0.01: continue
		cleaned.append(point)
	cleaned.append(cleaned[0])
	return cleaned

static func _point_along_loop(points: PackedVector3Array, start: int, distance: float) -> Vector3:
	var direction := 1 if distance>=0.0 else -1
	var remaining := absf(distance)
	var index := start
	for step in range(points.size()):
		var next := posmod(index+direction,points.size())
		var length := points[index].distance_to(points[next])
		if remaining<=length: return points[index].lerp(points[next],remaining/maxf(length,0.000001))
		remaining-=length
		index=next
	return points[start]

static func sample_path(raw: Array, spacing: float) -> Array[Dictionary]:
	var total := 0.0
	for i in range(1, raw.size()): total += Vector3(raw[i][0],raw[i][1],raw[i][2]).distance_to(Vector3(raw[i-1][0],raw[i-1][1],raw[i-1][2]))
	var count := maxi(1, ceili(total/spacing))
	var distance := 0.0
	var next := 0.0
	var result: Array[Dictionary] = []
	for i in range(1,raw.size()):
		var a := Vector3(raw[i-1][0],raw[i-1][1],raw[i-1][2])
		var b := Vector3(raw[i][0],raw[i][1],raw[i][2])
		var length := a.distance_to(b)
		while next <= distance+length and result.size() <= count:
			var point := a.lerp(b, clampf((next-distance)/maxf(length,0.00001),0,1))
			result.append({"point": point, "direction": (b-a).normalized()})
			next += total/count
		distance += length
	return result


static func _packed_subset(original: ArrayMesh, surface: int, selected: PackedInt32Array, indices: PackedInt32Array, vertices: PackedVector3Array) -> ArrayMesh:
	# Copy native packed records. Re-encoding normals or compressed positions
	# changes their values; retain the original quantization AABB/UV scale too.
	var source: Dictionary = (original.get("_surfaces") as Array)[surface]
	assert((source.get("skin_data",PackedByteArray()) as PackedByteArray).is_empty())
	var output := source.duplicate()
	var format: int = source.format
	var count: int = source.vertex_count
	var position_stride := RenderingServer.mesh_surface_get_format_vertex_stride(format,count)
	var normal_stride := RenderingServer.mesh_surface_get_format_normal_tangent_stride(format,count)
	var normal_offset := RenderingServer.mesh_surface_get_format_offset(format,count,Mesh.ARRAY_NORMAL)
	var data: PackedByteArray = source.vertex_data
	var packed := PackedByteArray()
	for index in selected: packed.append_array(data.slice(index*position_stride,(index+1)*position_stride))
	for index in selected: packed.append_array(data.slice(normal_offset+index*normal_stride,normal_offset+(index+1)*normal_stride))
	output.vertex_data = packed
	var attributes: PackedByteArray = source.get("attribute_data",PackedByteArray())
	var attribute_stride := RenderingServer.mesh_surface_get_format_attribute_stride(format,count)
	var packed_attributes := PackedByteArray()
	for index in selected: packed_attributes.append_array(attributes.slice(index*attribute_stride,(index+1)*attribute_stride))
	output.attribute_data = packed_attributes
	var index_bytes := PackedByteArray()
	var index_stride := 2 if selected.size() <= 65536 else 4
	index_bytes.resize(indices.size()*index_stride)
	for i in range(indices.size()):
		if index_stride == 2: index_bytes.encode_u16(i*2,indices[i])
		else: index_bytes.encode_u32(i*4,indices[i])
	output.index_data = index_bytes
	output.index_count = indices.size()
	output.vertex_count = selected.size()
	output.format = format | Mesh.ARRAY_FORMAT_INDEX
	output.lods = []
	var result := ArrayMesh.new()
	result.set("_surfaces",[output])
	var bounds := AABB(vertices[selected[0]],Vector3.ZERO)
	for index in selected: bounds=bounds.expand(vertices[index])
	result.custom_aabb = bounds
	return result


static func inside_planting(boundaries: Array, point: Vector2) -> bool:
	var inside := false
	for entry: Dictionary in boundaries:
		var polygon := PackedVector2Array()
		for value: Array in entry["points"]: polygon.append(Vector2(value[0], value[1]))
		if Geometry2D.is_point_in_polygon(point, polygon):
			if bool(entry["hole"]): return false
			inside = true
	return inside

static func planting_edge(boundaries: Array, seed: Vector2) -> Vector2:
	var result := Vector2(INF,INF)
	var best := INF
	for entry: Dictionary in boundaries:
		var points: Array = entry["points"]
		for i in range(points.size()):
			var a := Vector2(points[i][0],points[i][1])
			var b := Vector2(points[(i+1)%points.size()][0],points[(i+1)%points.size()][1])
			var edge := Geometry2D.get_closest_point_to_segment(seed,a,b)
			var normal := Vector2(-(b-a).y,(b-a).x).normalized()*0.6
			for candidate: Vector2 in [edge+normal,edge-normal]:
				var distance := candidate.distance_squared_to(seed)
				if distance < best and inside_planting(boundaries, candidate):
					best = distance
					result = candidate
	return result
