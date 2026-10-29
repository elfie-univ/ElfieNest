extends Node3D
## Explicit local animation candidate, sampled by the owning review clock.
## The sidecar's 200 authored spray instances and all source meshes stay static.

const DROPLETS_PER_CONTACT := 4
var impact_points := PackedVector3Array()
var pool_bounds := AABB()
var _droplets: MultiMeshInstance3D


func bind(geometry: Node3D) -> Dictionary:
	if is_instance_valid(_droplets):
		_droplets.free()
	impact_points.clear()
	var pool := geometry.find_child("Reference fountain water", true, false) as MeshInstance3D
	var source_spray := geometry.find_child("__ELFIE_INST_GROUP_133", true, false) as MeshInstance3D
	assert(pool != null and source_spray != null, "Splash needs the actual pool and authored spray template before review cropping")
	pool_bounds = pool.global_transform * pool.get_aabb()
	var center := pool_bounds.get_center()
	for mesh: MeshInstance3D in geometry.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		var material := mesh.get_active_material(0)
		if material == null or material.get_meta("estate_water_role", "") != "jet":
			continue
		var bounds := mesh.global_transform * mesh.get_aabb()
		var middle := bounds.get_center()
		if middle.x < pool_bounds.position.x or middle.x > pool_bounds.end.x or middle.z < pool_bounds.position.z or middle.z > pool_bounds.end.z:
			continue
		# Each authored arc starts at the central nozzle and lands at its outer
		# low endpoint. Select the real low vertex farthest from the pool centre.
		var reach := -1.0
		var contact := Vector3.ZERO
		for surface in range(mesh.mesh.get_surface_count()):
			var vertices: PackedVector3Array = mesh.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
			for vertex: Vector3 in vertices:
				var point := mesh.to_global(vertex)
				if absf(point.y - pool_bounds.position.y) > 0.04:
					continue
				var distance := Vector2(point.x - center.x, point.z - center.z).length_squared()
				if distance > reach:
					reach = distance
					contact = point
		if reach > 0.0:
			contact.y = pool_bounds.position.y + 0.008
			impact_points.append(contact)
	assert(impact_points.size() == 10, "Splash needs ten actual fountain arcs, excluding the spillway fall")
	var source_material := source_spray.get_active_material(0) as BaseMaterial3D
	assert(source_material != null, "Splash template must retain its authored source material")
	var owned := source_material.duplicate() as BaseMaterial3D
	owned.vertex_color_use_as_albedo = true
	var instances := MultiMesh.new()
	instances.transform_format = MultiMesh.TRANSFORM_3D
	instances.use_colors = true
	instances.mesh = source_spray.mesh
	instances.instance_count = impact_points.size() * DROPLETS_PER_CONTACT
	_droplets = MultiMeshInstance3D.new()
	_droplets.name = "ContactSplashDroplets"
	_droplets.multimesh = instances
	_droplets.material_override = owned
	_droplets.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_droplets.layers = source_spray.layers
	add_child(_droplets)
	sample(0.0)
	return {"impacts": impact_points.size(), "droplets": instances.instance_count}


func sample(seconds: float) -> void:
	if not is_instance_valid(_droplets):
		return
	_droplets.visible = true
	var buffer := PackedFloat32Array()
	buffer.resize(_droplets.multimesh.instance_count * 16)
	for index in range(_droplets.multimesh.instance_count):
		var contact_index := index / DROPLETS_PER_CONTACT
		var local_index := index % DROPLETS_PER_CONTACT
		var lifetime := 0.55 + float(contact_index % 3) * 0.025
		var phase := fposmod(seconds / lifetime + float(local_index) / DROPLETS_PER_CONTACT + float(contact_index) * 0.071, 1.0)
		var angle := TAU * (float(local_index) / DROPLETS_PER_CONTACT + float(contact_index) * 0.137)
		var outward := Vector3(cos(angle), 0.0, sin(angle))
		var position := impact_points[contact_index] + outward * (0.18 * phase)
		position.y += 4.0 * (0.14 + float(local_index % 2) * 0.02) * phase * (1.0 - phase)
		var local := _droplets.to_local(position)
		var offset := index * 16
		buffer[offset] = 0.012
		buffer[offset + 3] = local.x
		buffer[offset + 5] = 0.023
		buffer[offset + 7] = local.y
		buffer[offset + 10] = 0.012
		buffer[offset + 11] = local.z
		buffer[offset + 12] = 1.0
		buffer[offset + 13] = 1.0
		buffer[offset + 14] = 1.0
		buffer[offset + 15] = smoothstep(0.0, 0.08, phase) * (1.0 - smoothstep(0.75, 1.0, phase))
	# The existing estate sidecar uses this same retained buffer submission.
	# It also avoids per-particle RenderingServer calls for the local animation.
	_droplets.multimesh.buffer = buffer


func clear() -> void:
	if is_instance_valid(_droplets):
		_droplets.visible = false
