extends RefCounted
## Deform one owned instance of the authored duvet; preserve its UVs/material.
const CELL := 0.035
var cloth: MeshInstance3D
var original: Mesh
var authored_mesh: Mesh
var _arrays: Array
var _rest := PackedVector3Array()
var _source_top: Dictionary = {}
var _posed := PackedVector3Array()
var _folded := PackedVector3Array()
var _folded_empty := PackedVector3Array()
var _dynamic := ArrayMesh.new()
var _bounds: AABB
var _last := Vector2(-1, -1)
var _neighbors: Array[PackedInt32Array] = []

func bind(value: MeshInstance3D) -> void:
	cloth = value
	authored_mesh = cloth.mesh
	original = authored_mesh
	_arrays = original.surface_get_arrays(0).duplicate(true)
	_rest = _arrays[Mesh.ARRAY_VERTEX]
	_bounds = original.get_aabb()
	# The authored 23 cm quilting was rejected. Keep this same cloth object,
	# outline, UVs and material, but give its resting panel a thin fabric profile.
	for i in range(_rest.size()):
		var point := _rest[i]
		var ripple := sin(point.z*47.0+point.x*10.0+sin(point.x*21.0)*0.25)*0.0028
		ripple += sin(point.x*62.0+point.z*13.0)*0.0015
		ripple += sin(point.z*83.0-point.x*23.0)*0.0008
		point.y = _bounds.position.y+0.055+(point.y-_bounds.position.y)*0.025+ripple
		_rest[i] = point
	var refined := ArrayMesh.new()
	_arrays[Mesh.ARRAY_VERTEX] = _rest
	_arrays[Mesh.ARRAY_NORMAL] = _normals(_rest)
	_arrays[Mesh.ARRAY_TANGENT] = null
	refined.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,_arrays)
	refined.surface_set_material(0,authored_mesh.surface_get_material(0))
	original = refined
	cloth.mesh = original
	_bounds = original.get_aabb()
	for point: Vector3 in _rest:
		_insert_peak(_source_top, point)
	_neighbors.resize(_rest.size())
	var indices: PackedInt32Array = _arrays[Mesh.ARRAY_INDEX]
	for i in range(0,indices.size(),3):
		for a: int in [indices[i],indices[i+1],indices[i+2]]:
			for b: int in [indices[i],indices[i+1],indices[i+2]]:
				if a != b and not _neighbors[a].has(b): _neighbors[a].append(b)

func build_pose(body: Node3D, skeleton: Skeleton3D) -> void:
	var skin := skin_points(body, skeleton, true)
	var top: Dictionary = {}
	for point: Vector3 in skin:
		_insert_peak(top, cloth.to_local(point))
	_posed.clear()
	_folded.clear()
	_folded_empty.clear()
	var chest := cloth.to_local(_bone(skeleton, "Spine2"))
	var neck := cloth.to_local(_bone(skeleton, "Neck"))
	var head_edge := lerpf(chest.z, neck.z, 0.55)
	var foot_edge := _bounds.end.z + 0.04
	for point: Vector3 in _rest:
		var u := (point.z - _bounds.position.z) / _bounds.size.z
		var source_height := _peak(_source_top, point, 1)
		var raised := point
		raised.z = lerpf(head_edge, foot_edge, u)
		var height := _peak(top, raised, 2)
		# A loose span falls diagonally from the body toward the bed edge.
		# Do not shrink-wrap each limb or inflate the whole foot area.
		var center_x := _bounds.get_center().x
		var side := (_bounds.end.x-center_x) if raised.x>=center_x else (center_x-_bounds.position.x)
		var span := 1.0-clampf((absf(raised.x-center_x)-0.14)/(side-0.14),0.0,1.0)
		var ridge := _peak(top,Vector3(center_x,raised.y,raised.z),5)
		height = maxf(height+0.018,lerpf(source_height,ridge+0.045,span))
		raised.y += maxf(0.0,height-source_height)
		_posed.append(raised)
		var folded := point
		folded.z = lerpf(0.075, foot_edge, u)
		var empty_fold := folded
		empty_fold.y += sin(u*PI)*0.012
		_folded_empty.append(empty_fold)
		folded.y += maxf(0.0, _peak(top, folded, 3) + 0.025 - source_height)
		folded.y += sin(u * PI) * 0.025
		_folded.append(folded)
	_fit_contacts(_posed, skin)
	_soften_lift(_posed)
	_last = Vector2(-1, -1)

func _soften_lift(vertices: PackedVector3Array) -> void:
	# Spread contact corrections with a rounded falloff. Keep all verified skin
	# clearances; only lift neighboring cloth and retain its small fabric wrinkles.
	var lift := PackedFloat32Array()
	for i in range(_rest.size()): lift.append(vertices[i].y-_rest[i].y)
	for pass_index in range(7):
		var next := lift.duplicate()
		for i in range(lift.size()):
			for neighbor: int in _neighbors[i]:
				var distance := Vector2(vertices[i].x-vertices[neighbor].x, vertices[i].z-vertices[neighbor].z).length_squared()
				next[i] = maxf(next[i], lift[neighbor]-distance/0.08)
		lift = next
	for i in range(vertices.size()): vertices[i].y = _rest[i].y+lift[i]

func _fit_contacts(vertices: PackedVector3Array, skin: PackedVector3Array) -> void:
	# Correct only real skin/cloth intersections, retaining the authored topology.
	var cells: Dictionary = {}
	var indices: PackedInt32Array = _arrays[Mesh.ARRAY_INDEX]
	for index in range(0,indices.size(),3):
		var triangle := PackedInt32Array([indices[index],indices[index+1],indices[index+2]])
		var a := vertices[triangle[0]]
		var b := vertices[triangle[1]]
		var c := vertices[triangle[2]]
		for x in range(floori(minf(a.x,minf(b.x,c.x))/CELL),floori(maxf(a.x,maxf(b.x,c.x))/CELL)+1):
			for z in range(floori(minf(a.z,minf(b.z,c.z))/CELL),floori(maxf(a.z,maxf(b.z,c.z))/CELL)+1):
				var key := Vector2i(x,z)
				if not cells.has(key): cells[key] = []
				cells[key].append(triangle)
	for world: Vector3 in skin:
		var point := cloth.to_local(world)
		var key := Vector2i(floori(point.x/CELL),floori(point.z/CELL))
		var height := -INF
		var upper := PackedInt32Array()
		for triangle: PackedInt32Array in cells.get(key,[]):
			var hit: Variant = Geometry3D.ray_intersects_triangle(Vector3(point.x,10,point.z),Vector3.DOWN,vertices[triangle[0]],vertices[triangle[1]],vertices[triangle[2]])
			if hit is Vector3 and (hit as Vector3).y > height:
				height = (hit as Vector3).y
				upper = triangle
		if upper.is_empty() or height >= point.y + 0.012: continue
		for corner: int in upper:
			vertices[corner].y += point.y + 0.012 - height

func sample(cover: float, open_amount: float, lift: float, breath: float, body_weight: float = 1.0) -> void:
	if cover <= 0.0 and open_amount <= 0.0:
		cloth.mesh = original
		_last = Vector2(-1, -1)
		return
	var vertices := PackedVector3Array()
	for i in range(_rest.size()):
		var folded := _folded_empty[i].lerp(_folded[i],body_weight)
		var point := _rest[i].lerp(folded, open_amount).lerp(_posed[i], cover)
		var u := float((_rest[i].z - _bounds.position.z) / _bounds.size.z)
		point.y += lift * (1.0 - u) + breath * sin(u * PI) * cover
		vertices.append(point)
	var arrays := _arrays.duplicate()
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = _normals(vertices)
	# Original tangents no longer match the deformed silhouette. Keep original UVs.
	arrays[Mesh.ARRAY_TANGENT] = null
	_dynamic.clear_surfaces()
	_dynamic.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_dynamic.surface_set_material(0, original.surface_get_material(0))
	cloth.mesh = _dynamic

func pin_grip(index: int, target: Vector3, weight: float) -> void:
	# The held original hem follows the solved real wrist. Adjacent cloth falls
	# off from this attachment; no second cloth or detached floating grip is used.
	var arrays := cloth.mesh.surface_get_arrays(0).duplicate()
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var delta := (target-vertices[index])*weight
	var grab_u := (_rest[index].z-_bounds.position.z)/_bounds.size.z
	for i in range(vertices.size()):
		var u := (_rest[i].z-_bounds.position.z)/_bounds.size.z
		var x := (_rest[i].x-_rest[index].x)/0.24
		vertices[i] += delta*exp(-x*x)*pow(clampf((1.0-u)/(1.0-grab_u),0.0,1.0),3.0)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = _normals(vertices)
	_dynamic.clear_surfaces()
	_dynamic.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	_dynamic.surface_set_material(0,original.surface_get_material(0))
	cloth.mesh = _dynamic

func _normals(points: PackedVector3Array) -> PackedVector3Array:
	var result := PackedVector3Array()
	result.resize(points.size())
	var indices: PackedInt32Array = _arrays[Mesh.ARRAY_INDEX]
	var source_normals: PackedVector3Array = _arrays[Mesh.ARRAY_NORMAL]
	for i in range(0, indices.size(), 3):
		var a := indices[i]
		var b := indices[i+1]
		var c := indices[i+2]
		var n := (points[b]-points[a]).cross(points[c]-points[a])
		var old := (_rest[b]-_rest[a]).cross(_rest[c]-_rest[a])
		if old.dot(source_normals[a] + source_normals[b] + source_normals[c]) < 0.0:
			n = -n
		result[a] += n
		result[b] += n
		result[c] += n
	for i in range(result.size()):
		result[i] = result[i].normalized()
	return result

static func _insert_peak(field: Dictionary, point: Vector3) -> void:
	var cell := Vector2i(roundi(point.x / CELL), roundi(point.z / CELL))
	field[cell] = maxf(float(field.get(cell, -10.0)), point.y)

static func _peak(field: Dictionary, point: Vector3, radius: int) -> float:
	var center := Vector2i(roundi(point.x / CELL), roundi(point.z / CELL))
	var value := -10.0
	for x in range(-radius, radius+1):
		for z in range(-radius, radius+1):
			var key := center + Vector2i(x,z)
			if not field.has(key): continue
			var distance := Vector2(point.x-key.x*CELL, point.z-key.y*CELL).length_squared()
			value = maxf(value, float(field[key]) - distance / 0.045)
	return value

static func skin_points(body: Node3D, skeleton: Skeleton3D, omit_head: bool = false) -> PackedVector3Array:
	var result := PackedVector3Array()
	for mesh: MeshInstance3D in body.find_children("*", "MeshInstance3D", true, false):
		if mesh.skin == null or mesh.mesh == null: continue
		var matrices: Array[Transform3D] = []
		var is_head: Array[bool] = []
		for binding in range(mesh.skin.get_bind_count()):
			var name := String(mesh.skin.get_bind_name(binding))
			var bone := skeleton.find_bone(name) if not name.is_empty() else mesh.skin.get_bind_bone(binding)
			var label := skeleton.get_bone_name(bone)
			is_head.append("Head" in label or "Neck" in label or "Eye" in label or "Jaw" in label)
			matrices.append(skeleton.global_transform * skeleton.get_bone_global_pose(bone) * mesh.skin.get_bind_pose(binding))
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var stride := bones.size() / points.size()
			for index in range(points.size()):
				var point := Vector3.ZERO
				var head_weight := 0.0
				for slot in range(stride):
					var bind := bones[index*stride+slot]
					var weight := weights[index*stride+slot]
					point += (matrices[bind] * points[index]) * weight
					if is_head[bind]: head_weight += weight
				if not omit_head or head_weight < 0.5: result.append(point)
	return result

static func _bone(skeleton: Skeleton3D, suffix: String) -> Vector3:
	for index in range(skeleton.get_bone_count()):
		if skeleton.get_bone_name(index).ends_with(suffix):
			return skeleton.to_global(skeleton.get_bone_global_pose(index).origin)
	return Vector3.ZERO
