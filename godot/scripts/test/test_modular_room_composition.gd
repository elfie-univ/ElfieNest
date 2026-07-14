extends SceneTree

const DORM_SCENE := preload("res://modular_rooms/dorm_room.tscn")
const ACTIVITY_SCENE := preload("res://modular_rooms/activity_room.tscn")
const PORTAL_SCENE := preload("res://modular_rooms/portal_room.tscn")
const NEST_SCENE := preload("res://modular_rooms/modular_nest_demo.tscn")
const G := preload("res://modular_rooms/modular_geometry.gd")
const D := preload("res://modular_rooms/room_dimensions.gd")

const EXPECTED_BED_ROTATIONS := [
	Vector3(0.0, 90.0, 180.0),
	Vector3(0.0, 90.0, 0.0),
	Vector3(0.0, -90.0, 0.0),
	Vector3(0.0, -90.0, -180.0),
]
const EXPECTED_BED_SCALES := [
	Vector3(-0.7, -0.7, -0.7),
	Vector3(0.7, 0.7, 0.7),
	Vector3(0.7, 0.7, 0.7),
	Vector3(-0.7, -0.7, -0.7),
]
const EXPECTED_ACTIVITY_SCENE_PATHS := [
	"res://room/common_area/1_kitchen_room.tscn",
	"res://room/common_area/2_sitting_room.tscn",
	"res://room/common_area/3_media_room.tscn",
	"res://room/common_area/4_gym.tscn",
	"res://room/common_area/5_garden.tscn",
	"res://room/common_area/6_working_room.tscn",
	"res://room/common_area/7_music_room.tscn",
	"res://room/common_area/8_bookroom.tscn",
]


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var dorm_ok := await _test_dorm_preserves_source_bed_layout()
	if not dorm_ok:
		return
	var activity_ok := await _test_activity_uses_source_furniture_with_colliders()
	if not activity_ok:
		return
	var portal_ok := await _test_teleporter_is_centered_on_its_stage()
	if not portal_ok:
		return
	var capacity_ok := await _test_partial_dorm_and_eight_room_activity_boundaries()
	if not capacity_ok:
		return
	if not _test_wall_finishes_have_a_visible_clearance_from_the_core():
		return
	print("PASS: modular rooms preserve source furniture, collision, doorway, and wall separation")
	quit(0)


func _test_dorm_preserves_source_bed_layout() -> bool:
	var dorm := DORM_SCENE.instantiate() as ModularDormRoom
	dorm.auto_preview = false
	root.add_child(dorm)
	dorm.build(0)
	await process_frame
	var generated := dorm.get_node("Generated") as Node3D
	for index in range(4):
		var bed := generated.get_node("Bed_%02d" % (index + 1)) as Node3D
		if not _require(
			bed.rotation_degrees.is_equal_approx(EXPECTED_BED_ROTATIONS[index]),
			"Bed %d no longer preserves the ladder-facing rotation" % (index + 1)
		):
			return false
		if not _require(
			bed.scale.is_equal_approx(EXPECTED_BED_SCALES[index]),
			"Bed %d no longer preserves the source mirror transform" % (index + 1)
		):
			return false
	if not _require(_count_colliders(dorm) >= 9, "Dorm furniture and doorway do not have collision shapes"):
		return false
	if not _require(generated.has_node("DormDoorwayLeft"), "Dorm lacks the privacy doorway wall"):
		return false
	if not _require(generated.has_node("DormRug"), "Dorm lacks the central rug between its bed rows"):
		return false
	var interior_light := generated.get_node_or_null("DormInteriorLight") as OmniLight3D
	if not _require(interior_light != null, "Dorm lacks neutral interior lighting to keep wall colors consistent"):
		return false
	if not _require(
		is_equal_approx(interior_light.light_color.r, interior_light.light_color.g)
			and is_equal_approx(interior_light.light_color.g, interior_light.light_color.b),
		"Dorm interior light is tinted and changes the apparent wall color"
	):
		return false
	if not _require(generated.has_node("DormMuralFrame") and generated.has_node("DormMural"), "Dorm lacks the mural directly opposite its entry"):
		return false
	var mural_frame := generated.get_node("DormMuralFrame") as MeshInstance3D
	var mural := generated.get_node("DormMural") as MeshInstance3D
	if not _require(
		mural_frame.position.x > D.DORM_DEPTH / 2.0 - 0.18,
		"Dorm mural is not mounted on the wall opposite the entry"
	):
		return false
	var wall_finish_face_x := D.DORM_DEPTH / 2.0 - (
		D.WALL_THICKNESS / 2.0 + G.FINISH_AIR_GAP + G.FINISH_THICKNESS
	)
	var frame_half_depth := (mural_frame.mesh as BoxMesh).size.x / 2.0
	var frame_wall_gap := wall_finish_face_x - (mural_frame.position.x + frame_half_depth)
	var artwork_frame_gap := mural_frame.position.x - frame_half_depth - mural.position.x
	if not _require(
		absf(frame_wall_gap - 0.001) <= 0.0005,
		"Dorm mural frame leaves a %.4fm wall gap instead of 0.001m" % frame_wall_gap
	):
		return false
	if not _require(
		absf(artwork_frame_gap - 0.0005) <= 0.00025,
		"Dorm artwork leaves a %.4fm gap from its frame face instead of 0.0005m" % artwork_frame_gap
	):
		return false
	if not _require(is_equal_approx(D.DORM_DEPTH, 3.9), "Dorm depth no longer matches the compact two-bed layout"):
		return false
	var left_bed_bounds := G.visual_bounds_in(generated.get_node("Bed_01") as Node3D, generated)
	var right_bed_bounds := G.visual_bounds_in(generated.get_node("Bed_02") as Node3D, generated)
	var bed_pair_seam := right_bed_bounds.position.x - left_bed_bounds.end.x
	if not _require(
		absf(bed_pair_seam) <= 0.005,
		"Dorm bed pair leaves a %.3fm center seam instead of a zero-gap bed join" % bed_pair_seam
	):
		return false
	if not _require(
		left_bed_bounds.position.x - (-D.DORM_DEPTH / 2.0) <= 0.08
		and D.DORM_DEPTH / 2.0 - right_bed_bounds.end.x <= 0.08,
		"Dorm bed pair is not closely aligned with both room walls"
	):
		return false
	var positive_row := left_bed_bounds.merge(right_bed_bounds)
	var negative_row := G.visual_bounds_in(generated.get_node("Bed_03") as Node3D, generated).merge(
		G.visual_bounds_in(generated.get_node("Bed_04") as Node3D, generated)
	)
	var partition_face := D.CELL_PITCH / 2.0 - (
		D.WALL_THICKNESS / 2.0 + G.FINISH_AIR_GAP + G.FINISH_THICKNESS
	)
	var positive_wall_gap := partition_face - positive_row.end.z
	var negative_wall_gap := negative_row.position.z + partition_face
	if not _require(
		absf(positive_wall_gap - 0.001) <= 0.0005
			and absf(negative_wall_gap - 0.001) <= 0.0005,
		"Dorm bed rows leave %.4fm / %.4fm gaps from their partition walls" % [
			positive_wall_gap,
			negative_wall_gap,
		]
	):
		return false
	await physics_frame
	var first_bed := generated.get_node("Bed_01") as Node3D
	if not _require(
		_has_static_collision_at(dorm, first_bed.global_position + Vector3(0.0, 0.7, 0.0)),
		"A physics probe passes through the first dorm bed"
	):
		return false
	if not _require(
		_has_static_collision_at(dorm, dorm.to_global(Vector3(D.DORM_DEPTH / 2.0, 1.5, 0.0))),
		"A physics probe passes through the dorm outer wall"
	):
		return false
	dorm.free()
	return true


func _test_activity_uses_source_furniture_with_colliders() -> bool:
	for kind in range(8):
		var activity := ACTIVITY_SCENE.instantiate() as ModularActivityRoom
		activity.auto_preview = false
		root.add_child(activity)
		activity.build(Color("#ef8354"), kind)
		await process_frame
		var generated := activity.get_node("Generated") as Node3D
		if not _require(generated.has_node("SourceFurniture"), "Activity room still uses primitive placeholder furniture"):
			return false
		var minimum_collider_count := 4 if kind < 4 else 1
		if not _require(
			_count_colliders(activity) >= minimum_collider_count,
			"Activity room %d furniture has no collision coverage" % (kind + 1)
		):
			return false
		var source := generated.get_node("SourceFurniture/SourceRoom") as Node3D
		if not _require(
			source.scene_file_path == EXPECTED_ACTIVITY_SCENE_PATHS[kind],
			"Activity room %d does not use its corresponding source scene" % (kind + 1)
		):
			return false
		var content := _activity_content_root(source)
		if not _verify_activity_physical_dimensions(kind, content, generated):
			return false
		if not _verify_activity_wall_anchors(kind, content, generated):
			return false
		var bounds := G.visual_bounds_in(source, generated)
		var finish_depth := D.WALL_THICKNESS / 2.0 + G.FINISH_AIR_GAP + G.FINISH_THICKNESS
		var room_x_min := -D.ACTIVITY_DEPTH / 2.0 + finish_depth
		var room_x_max := D.ACTIVITY_DEPTH / 2.0
		var room_z_min := -D.CELL_PITCH / 2.0 + finish_depth
		var room_z_max := D.CELL_PITCH / 2.0 - finish_depth
		if not _require(
			bounds.position.x >= room_x_min - 0.002
				and bounds.end.x <= room_x_max + 0.002
				and bounds.position.z >= room_z_min - 0.002
				and bounds.end.z <= room_z_max + 0.002,
			"Activity room %d furniture crosses a visible room boundary: %s" % [kind + 1, bounds]
		):
			return false
		var original_source := load(EXPECTED_ACTIVITY_SCENE_PATHS[kind]).instantiate() as Node3D
		activity.add_child(original_source)
		await process_frame
		var original_envelope := G.visual_bounds_in(original_source, activity)
		var original_source_scale := original_source.scale
		activity.remove_child(original_source)
		original_source.queue_free()
		var source_scale_ratio := Vector3(
			source.scale.x / original_source_scale.x,
			source.scale.y / original_source_scale.y,
			source.scale.z / original_source_scale.z
		)
		var fitted_envelope := AABB(
			source.position + original_envelope.position * source_scale_ratio,
			original_envelope.size * source_scale_ratio.abs()
		)
		if not _require(
			is_equal_approx(fitted_envelope.position.x, -D.ACTIVITY_DEPTH / 2.0 + 0.06)
				and is_equal_approx(fitted_envelope.get_center().z, 0.0),
			"Activity room %d fits furniture-only bounds instead of preserving its original room envelope" % (kind + 1)
		):
			return false
		if kind == 4 and not _require(
			absf(bounds.position.z - (room_z_min + 0.001)) <= 0.002
				and absf(bounds.end.z - (room_z_max - 0.001)) <= 0.002,
			"Garden perimeter does not follow both side walls: %s" % bounds
		):
			return false
		activity.free()
	return true


func _test_teleporter_is_centered_on_its_stage() -> bool:
	var portal := PORTAL_SCENE.instantiate() as ModularPortalRoom
	portal.auto_preview = false
	root.add_child(portal)
	portal.build()
	await process_frame
	var generated := portal.get_node("Generated") as Node3D
	var teleporter := generated.get_node("Teleporter") as Node3D
	var ring := generated.get_node_or_null("TeleporterRingUnderlight") as MeshInstance3D
	var runway := generated.get_node_or_null("TeleporterRunwayUnderlight") as MeshInstance3D
	if not _require(ring != null and runway != null, "Teleporter base lacks its circular light and aligned approach runway"):
		return false
	if not _require(
		is_equal_approx(ring.position.x, teleporter.position.x)
			and is_equal_approx(ring.position.z, teleporter.position.z),
		"Teleporter circular underlight is not centered on the circular machine platform"
	):
		return false
	var runway_mesh := runway.mesh as BoxMesh
	if not _require(
		runway.position.z < ring.position.z
			and runway.position.z + runway_mesh.size.z / 2.0 > ring.position.z - (ring.mesh as CylinderMesh).bottom_radius,
		"Teleporter approach runway does not join the circular platform from the doorway side"
	):
		return false
	portal.free()
	return true


func _verify_activity_physical_dimensions(kind: int, content: Node3D, generated: Node3D) -> bool:
	match kind:
		0:
			var counter := _bounds(content, "Counter", generated)
			var refrigerator := _bounds(content, "Refrigerator", generated)
			var recycling_bins := _bounds(content, "Recycling_Bins", generated)
			var shelves := _bounds(content, "Shelves", generated)
			return _require(
				refrigerator.size.y >= 1.7
					and not _has_volume_overlap(counter, refrigerator)
					and not _has_volume_overlap(counter, recycling_bins)
					and not _has_volume_overlap(counter, shelves)
					and shelves.size.x <= 2.45,
				"Kitchen furniture still interpenetrates or the shelving run is too large"
			)
		1:
			return _require(
				_bounds(content, "Chair1", generated).size.y >= 0.75
					and _bounds(content, "Table", generated).size.y >= 0.70,
				"Dining furniture remains below usable seat/table height"
			)
		2:
			var sofa := _bounds(content, "Sofa", generated)
			var coffee_table := _bounds(content, "Coffee_Table", generated)
			return _require(
				sofa.size.y >= 0.80
					and coffee_table.size.y >= 0.35
					and coffee_table.size.y <= 0.50,
				"Media furniture proportions remain outside realistic ranges"
			)
		3:
			var treadmill := _bounds(content, "Treadmill", generated)
			var yoga_ball := _bounds(content, "YogaBall", generated)
			var second_yoga_ball := _bounds(content, "YogaBall1", generated)
			return _require(
				maxf(treadmill.size.x, treadmill.size.z) >= 1.65
					and maxf(yoga_ball.size.x, yoga_ball.size.z) <= 0.78
					and not _has_volume_overlap(yoga_ball, second_yoga_ball),
				"Gym equipment is still uniformly scaled instead of physically sized"
			)
		4:
			return _require(_bounds(content, "jardi", generated).size.y >= 1.5, "Garden plants remain vertically compressed")
		5:
			var curtains := content.get_node_or_null("Curtains") as Node3D
			return _require(
				_bounds(content, "Table", generated).size.y >= 0.70
					and _bounds(content, "Chair", generated).size.y >= 0.85
					and (curtains == null or not curtains.visible),
					"Working-room desks or chairs remain outside usable height ranges"
				)
		6:
				return _require(
					maxf(_bounds(content, "Drum_kit", generated).size.x, _bounds(content, "Drum_kit", generated).size.z) >= 1.65
						and maxf(_bounds(content, "piano", generated).size.x, _bounds(content, "piano", generated).size.z) >= 1.3
						and maxf(_bounds(content, "music_set", generated).size.x, _bounds(content, "music_set", generated).size.z) >= 2.9,
					"Music-room instruments remain visibly undersized"
				)
		7:
			return _require(
				_bounds(content, "Chair1", generated).size.y >= 0.75
					and _bounds(content, "Table", generated).size.y >= 0.70,
				"Bookroom reading furniture remains too small for human use"
			)
	return true


func _verify_activity_wall_anchors(kind: int, content: Node3D, generated: Node3D) -> bool:
	var anchors: Array = [
		[["Counter", "x_min"], ["Refrigerator", "x_min"], ["Picture5", "x_min"], ["Shelves", "x_max"]],
		[["Pictures", "z_max"], ["Pictures2", "z_min"], ["Wall_Shelves", "x_min"]],
		[["Pictures2", "x_min"], ["TV_Dresser", "z_max"]],
		[["Dumbell_Shelf", "x_min"], ["TV1", "z_min"], ["Cork_Board", "z_min"], ["Shelf", "z_max"]],
		[["jardi", "x_min"]],
		[["Wall_Shelves", "z_min"], ["Boards", "z_max"]],
		[],
		[["Bookshelf1", "z_max"], ["Bookshelf2", "x_min"], ["Bookshelf3", "z_min"], ["Bookshelf4", "z_min"]],
	]
	for entry in anchors[kind]:
		var gap := _target_wall_gap(_bounds(content, entry[0], generated), entry[1])
		if not _require(absf(gap - 0.001) <= 0.001, "Activity room %d %s leaves a %.3fm wall gap" % [kind + 1, entry[0], gap]):
			return false
	return true


func _activity_content_root(source: Node3D) -> Node3D:
	var converted := source.get_node_or_null("convert_node") as Node3D
	if converted != null:
		return converted
	var music_room := source.get_node_or_null("Room3") as Node3D
	return music_room if music_room != null else source


func _bounds(content: Node3D, child_name: String, reference: Node3D) -> AABB:
	return G.visual_bounds_in(content.get_node(child_name) as Node3D, reference)


func _target_wall_gap(bounds: AABB, wall: String) -> float:
	match wall:
		"x_min": return bounds.position.x - (-D.ACTIVITY_DEPTH / 2.0 + 0.062)
		"x_max": return D.ACTIVITY_DEPTH / 2.0 - 0.001 - bounds.end.x
		"z_min": return bounds.position.z - (-D.CELL_PITCH / 2.0 + 0.062)
		_: return D.CELL_PITCH / 2.0 - 0.062 - bounds.end.z


func _has_volume_overlap(first: AABB, second: AABB) -> bool:
	var overlap := Vector3(
		minf(first.end.x, second.end.x) - maxf(first.position.x, second.position.x),
		minf(first.end.y, second.end.y) - maxf(first.position.y, second.position.y),
		minf(first.end.z, second.end.z) - maxf(first.position.z, second.position.z)
	)
	return overlap.x > 0.01 and overlap.y > 0.01 and overlap.z > 0.01


func _test_partial_dorm_and_eight_room_activity_boundaries() -> bool:
	var demo_nest := NEST_SCENE.instantiate() as ModularNest
	root.add_child(demo_nest)
	await _wait_frames(3)
	var demo_generated := demo_nest.get_node("Generated") as Node3D
	if not _require(demo_nest.bed_count == 32, "Editor demo defaults to fewer than the full eight-room layout"):
		return false
	if not _require(_count_named_children(demo_generated, "DormRoom_") == 8, "Editor demo does not preview eight dorm rooms"):
		return false
	var fill_light := demo_nest.get_node("FillLight") as DirectionalLight3D
	var fill_color := fill_light.light_color
	if not _require(
		maxf(fill_color.r, maxf(fill_color.g, fill_color.b)) - minf(fill_color.r, minf(fill_color.g, fill_color.b)) <= 0.1,
		"Colored global fill light still makes identical dorm walls appear as different colors"
	):
		return false
	demo_nest.free()

	var partial_nest := NEST_SCENE.instantiate() as Node3D
	partial_nest.set("bed_count", 7)
	root.add_child(partial_nest)
	await _wait_frames(3)
	var partial_generated := partial_nest.get_node("Generated") as Node3D
	var final_dorm := partial_generated.get_node("DormRoom_02/Generated") as Node3D
	var partial_bed_count := _count_beds(final_dorm)
	if not _require(partial_bed_count == 3, "Seven beds generated %d beds in the second dorm instead of 3" % partial_bed_count):
		return false
	partial_nest.free()

	var full_nest := NEST_SCENE.instantiate() as Node3D
	full_nest.set("bed_count", 32)
	root.add_child(full_nest)
	await _wait_frames(3)
	var full_generated := full_nest.get_node("Generated") as Node3D
	if not _require(_count_named_children(full_generated, "ActivityRoom_") == 8, "Thirty-two beds did not generate eight activity rooms"):
		return false
	if not _require(full_generated.has_node("CorridorCentralMarble"), "Corridor lacks the light marble center field"):
		return false
	if not _require(
		full_generated.has_node("CorridorDarkMarbleBandLeft") and full_generated.has_node("CorridorDarkMarbleBandRight"),
		"Corridor lacks the darker marble border bands"
	):
		return false
	if not _require(not full_generated.has_node("ActivityPartition_01"), "The kitchen and second activity room should share an open boundary"):
		return false
	for boundary_index in range(2, 8):
		if not _require(full_generated.has_node("ActivityPartition_%02d" % boundary_index), "Activity boundary %d should have a wall" % boundary_index):
			return false
	full_nest.free()
	return true


func _test_wall_finishes_have_a_visible_clearance_from_the_core() -> bool:
	var parent := Node3D.new()
	root.add_child(parent)
	var wall := G.add_wall(
		parent,
		"WallUnderTest",
		Vector3(0.1, 3.0, 2.0),
		Vector3.ZERO,
		Color.WHITE,
		Color.BLACK
	)
	var core := wall.get_node("WallCore") as MeshInstance3D
	var finish := wall.get_node("PositiveFinish") as MeshInstance3D
	var core_size := (core.mesh as BoxMesh).size
	var finish_size := (finish.mesh as BoxMesh).size
	var clearance := absf(finish.position.x) - core_size.x / 2.0 - finish_size.x / 2.0
	if not _require(clearance >= 0.002, "Wall finish is coplanar with the wall core and can produce seam artifacts"):
		return false
	parent.free()
	return true


func _count_colliders(node: Node) -> int:
	var count := 1 if node is CollisionShape3D else 0
	for child in node.get_children():
		count += _count_colliders(child)
	return count


func _count_beds(node: Node) -> int:
	var count := 0
	for child in node.get_children():
		if String(child.name).match("Bed_??"):
			count += 1
	return count


func _count_named_children(node: Node, prefix: String) -> int:
	var count := 0
	for child in node.get_children():
		if child.name.begins_with(prefix):
			count += 1
	return count


func _wait_frames(count: int) -> void:
	for frame in range(count):
		await process_frame


func _has_static_collision_at(node: Node3D, point: Vector3) -> bool:
	var probe_shape := BoxShape3D.new()
	probe_shape.size = Vector3(0.18, 0.18, 0.18)
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = probe_shape
	query.transform = Transform3D(Basis.IDENTITY, point)
	query.collide_with_bodies = true
	query.collide_with_areas = false
	var hits := node.get_world_3d().direct_space_state.intersect_shape(query, 8)
	for hit in hits:
		if hit.collider is StaticBody3D:
			return true
	return false


func _require(condition: bool, message: String) -> bool:
	if condition:
		return true
	push_error(message)
	quit(1)
	return false
