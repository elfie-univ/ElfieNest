@tool
class_name ModularGeometry
extends RefCounted

const FINISH_THICKNESS: float = 0.008
const FINISH_INSET: float = 0.06
const FINISH_AIR_GAP: float = 0.004
const CORE_COLOR := Color("#36414a")


static func material(
	color: Color,
	emission_energy: float = 0.0,
	surface_roughness: float = 0.76
) -> StandardMaterial3D:
	var result := StandardMaterial3D.new()
	result.albedo_color = color
	result.roughness = surface_roughness
	if emission_energy > 0.0:
		result.emission_enabled = true
		result.emission = color
		result.emission_energy_multiplier = emission_energy
	return result


static func add_box(
	parent: Node3D,
	box_name: String,
	size: Vector3,
	position: Vector3,
	color: Color,
	with_collision: bool = false,
	emission_energy: float = 0.0,
	surface_roughness: float = 0.76
) -> MeshInstance3D:
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = box_name
	var box_mesh := BoxMesh.new()
	box_mesh.size = size
	mesh_instance.mesh = box_mesh
	mesh_instance.position = position
	mesh_instance.material_override = material(color, emission_energy, surface_roughness)
	mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	parent.add_child(mesh_instance)
	if with_collision:
		var body := StaticBody3D.new()
		body.name = "%sBody" % box_name
		body.position = position
		var collision := CollisionShape3D.new()
		collision.name = "%sCollision" % box_name
		var shape := BoxShape3D.new()
		shape.size = size
		collision.shape = shape
		body.add_child(collision)
		parent.add_child(body)
	return mesh_instance


static func add_cylinder(
	parent: Node3D,
	mesh_name: String,
	radius: float,
	height: float,
	position: Vector3,
	color: Color,
	emission_energy: float = 0.0,
	with_collision: bool = false
) -> MeshInstance3D:
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = mesh_name
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = radius
	cylinder.bottom_radius = radius
	cylinder.height = height
	mesh_instance.mesh = cylinder
	mesh_instance.position = position
	mesh_instance.material_override = material(color, emission_energy)
	parent.add_child(mesh_instance)
	if with_collision:
		var body := StaticBody3D.new()
		body.name = "%sBody" % mesh_name
		body.position = position
		var collision := CollisionShape3D.new()
		collision.name = "%sCollision" % mesh_name
		var shape := CylinderShape3D.new()
		shape.radius = radius
		shape.height = height
		collision.shape = shape
		body.add_child(collision)
		parent.add_child(body)
	return mesh_instance


static func add_wall(
	parent: Node3D,
	wall_name: String,
	size: Vector3,
	position: Vector3,
	negative_side_color: Color,
	positive_side_color: Color
) -> Node3D:
	var wall := Node3D.new()
	wall.name = wall_name
	wall.position = position
	parent.add_child(wall)
	add_box(wall, "WallCore", size, Vector3.ZERO, CORE_COLOR, true)

	var panel_size := size
	panel_size.y = maxf(0.05, panel_size.y - FINISH_INSET)
	if size.x <= size.z:
		panel_size.x = FINISH_THICKNESS
		panel_size.z = maxf(0.05, panel_size.z - FINISH_INSET)
		var offset_x := size.x / 2.0 + FINISH_AIR_GAP + FINISH_THICKNESS / 2.0
		add_box(wall, "NegativeFinish", panel_size, Vector3(-offset_x, 0.0, 0.0), negative_side_color)
		add_box(wall, "PositiveFinish", panel_size, Vector3(offset_x, 0.0, 0.0), positive_side_color)
	else:
		panel_size.x = maxf(0.05, panel_size.x - FINISH_INSET)
		panel_size.z = FINISH_THICKNESS
		var offset_z := size.z / 2.0 + FINISH_AIR_GAP + FINISH_THICKNESS / 2.0
		add_box(wall, "NegativeFinish", panel_size, Vector3(0.0, 0.0, -offset_z), negative_side_color)
		add_box(wall, "PositiveFinish", panel_size, Vector3(0.0, 0.0, offset_z), positive_side_color)
	return wall


static func add_floor(
	parent: Node3D,
	floor_name: String,
	size_x: float,
	size_z: float,
	position: Vector3,
	color: Color
) -> void:
	add_box(
		parent,
		floor_name,
		Vector3(size_x, ModularRoomDimensions.WALL_THICKNESS, size_z),
		position + Vector3(0.0, -ModularRoomDimensions.WALL_THICKNESS / 2.0, 0.0),
		color,
		true
	)


static func add_visual_bounds_collision(parent: Node3D, collision_name: String, source: Node3D) -> void:
	var bounds := visual_bounds_in(source, parent)
	if bounds.size.x < 0.05 or bounds.size.y < 0.05 or bounds.size.z < 0.05:
		return
	var body := StaticBody3D.new()
	body.name = "%sBody" % collision_name
	body.position = bounds.get_center()
	var collision := CollisionShape3D.new()
	collision.name = "%sShape" % collision_name
	var shape := BoxShape3D.new()
	shape.size = bounds.size
	collision.shape = shape
	body.add_child(collision)
	parent.add_child(body)


static func visual_bounds_in(source: Node3D, reference: Node3D) -> AABB:
	var meshes: Array[MeshInstance3D] = []
	_collect_mesh_instances(source, meshes)
	var has_bounds := false
	var bounds := AABB()
	for mesh in meshes:
		if not mesh.is_visible_in_tree():
			continue
		var mesh_bounds := mesh.get_aabb()
		for x_position in [mesh_bounds.position.x, mesh_bounds.end.x]:
			for y_position in [mesh_bounds.position.y, mesh_bounds.end.y]:
				for z_position in [mesh_bounds.position.z, mesh_bounds.end.z]:
					var point := reference.to_local(mesh.to_global(Vector3(x_position, y_position, z_position)))
					if not has_bounds:
						bounds = AABB(point, Vector3.ZERO)
						has_bounds = true
					else:
						bounds = bounds.expand(point)
	return bounds


static func _collect_mesh_instances(node: Node, result: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		result.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_mesh_instances(child, result)
