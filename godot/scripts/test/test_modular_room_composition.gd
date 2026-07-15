extends SceneTree

const DORM_SCENE := preload("res://rooms/dorm_room.tscn")
const ACTIVITY_SCENE := preload("res://rooms/activity_room.tscn")
const PORTAL_SCENE := preload("res://rooms/portal_room.tscn")
const NEST_SCENE := preload("res://rooms/nest.tscn")
const G := preload("res://rooms/room_geometry.gd")
const D := preload("res://rooms/room_dimensions.gd")

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
	"res://rooms/common_area_layouts/kitchen_layout.tscn",
	"res://rooms/common_area_layouts/sitting_layout.tscn",
	"res://rooms/common_area_layouts/media_layout.tscn",
	"res://rooms/common_area_layouts/gym_layout.tscn",
	"res://rooms/common_area_layouts/garden_layout.tscn",
	"res://rooms/common_area_layouts/working_layout.tscn",
	"res://rooms/common_area_layouts/music_layout.tscn",
	"res://rooms/common_area_layouts/bookroom_layout.tscn",
]


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var door_header_ok := await _test_dorm_door_header_has_no_overlapping_meshes()
	if not door_header_ok:
		return
	var floor_height_ok := await _test_decorative_floor_surfaces_stay_within_one_millimeter()
	if not floor_height_ok:
		return
	var dorm_ok := await _test_dorm_preserves_source_bed_layout()
	if not dorm_ok:
		return
	var mural_ok := await _test_dorm_murals_face_inward_and_are_stable_by_room()
	if not mural_ok:
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


func _test_dorm_door_header_has_no_overlapping_meshes() -> bool:
	var dorm := DORM_SCENE.instantiate() as ModularDormRoom
	dorm.auto_preview = false
	root.add_child(dorm)
	dorm.build(0)
	await process_frame
	var generated := dorm.get_node("Generated") as Node3D
	var track := generated.get_node("DormDoorTrack") as MeshInstance3D
	var header := generated.get_node("DormDoorHeaderTrim") as MeshInstance3D
	var overlap := G.visual_bounds_in(track, generated).intersection(G.visual_bounds_in(header, generated))
	if not _require(
		not overlap.has_volume(),
		"Dorm door header can flicker because it overlaps the track by %s" % overlap.size
	):
		return false
	dorm.free()
	return true


func _test_dorm_murals_face_inward_and_are_stable_by_room() -> bool:
	var dorm := DORM_SCENE.instantiate() as ModularDormRoom
	dorm.auto_preview = false
	root.add_child(dorm)
	dorm.build(0)
	await process_frame
	var first_mural := dorm.get_node("Generated/DormMural") as MeshInstance3D
	if not _require(
		first_mural.transform.basis.z.dot(Vector3.LEFT) > 0.99,
		"Dorm mural faces the exterior, so its texture appears mirrored inside the room"
	):
		return false
	var first_path := _dorm_mural_path(dorm)
	dorm.build(0)
	await process_frame
	var repeated_path := _dorm_mural_path(dorm)
	dorm.build(1)
	await process_frame
	var second_path := _dorm_mural_path(dorm)
	if not _require(first_path == repeated_path, "A dorm changes its mural when rebuilt with the same room index"):
		return false
	if not _require(first_path != second_path, "Adjacent dorm rooms use the same gallery mural"):
		return false
	if not _require(
		first_path.begins_with("res://rooms/assets/artwork/gallery/") and not first_path.ends_with("img1.jpg"),
		"Dorm murals do not use the curated oil-painting gallery"
	):
		return false
	dorm.free()
	return true


func _test_decorative_floor_surfaces_stay_within_one_millimeter() -> bool:
	var dorm := DORM_SCENE.instantiate() as ModularDormRoom
	dorm.auto_preview = false
	root.add_child(dorm)
	dorm.build(0)
	await process_frame
	var dorm_generated := dorm.get_node("Generated") as Node3D
	for node_name in ["DormRug", "DormRugOuterTrim", "DormRugInset"]:
		if not _require(_surface_is_flat(dorm_generated, node_name), "%s rises more than 1 mm above the dorm floor" % node_name):
			return false
	dorm.free()

	var nest := NEST_SCENE.instantiate() as Node3D
	root.add_child(nest)
	await _wait_frames(3)
	var generated := nest.get_node("Generated") as Node3D
	for node_name in [
		"CorridorCentralMarble",
		"CorridorWarmMarbleInlayLeft",
		"CorridorWarmMarbleInlayRight",
		"CorridorDarkMarbleBandLeft",
		"CorridorDarkMarbleBandRight",
		"CorridorOuterMarbleBorderLeft",
		"CorridorOuterMarbleBorderRight",
		"CorridorCentralTileJoint_00_0",
		"CorridorCentralTileJoint_00_1",
		"DormDoorwayInlay_00",
	]:
		if not _require(_surface_is_flat(generated, node_name), "%s rises more than 1 mm above the corridor floor" % node_name):
			return false
	nest.free()
	return true


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
	var doorway_lintel := generated.get_node("DormDoorwayLintel") as Node3D
	var lintel_core := doorway_lintel.get_node("WallCore") as MeshInstance3D
	var lintel_bottom_y := doorway_lintel.position.y - (lintel_core.mesh as BoxMesh).size.y / 2.0
	var door_track := generated.get_node("DormDoorTrack") as MeshInstance3D
	var door_header := generated.get_node("DormDoorHeaderTrim") as MeshInstance3D
	var track_top_y := door_track.position.y + (door_track.mesh as BoxMesh).size.y / 2.0
	var header_size := (door_header.mesh as BoxMesh).size
	var header_bottom_y := door_header.position.y - header_size.y / 2.0
	var header_top_y := door_header.position.y + header_size.y / 2.0
	if not _require(
		header_top_y >= lintel_bottom_y and header_bottom_y - track_top_y <= 0.001,
		"Dorm doorway header trim leaves a gap larger than 1 mm below the lintel or above the track"
	):
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
		var furniture_root := generated.get_node("SourceFurniture") as Node3D
		if not _require(
			furniture_root.transform.is_equal_approx(Transform3D.IDENTITY),
			"Activity room %d changes the authored layout container transform" % (kind + 1)
		):
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
		if kind == 1 or kind == 2:
			var artworks: Array[MeshInstance3D] = []
			_collect_gallery_artworks(source, artworks)
			if not _require(artworks.size() == 8, "Activity room %d does not fill all 8 picture frames" % (kind + 1)):
				return false
			var expected_prefix := "living_" if kind == 1 else "tv_"
			for artwork in artworks:
				var quad := artwork.mesh as QuadMesh
				var material := quad.material as StandardMaterial3D
				var texture_path := material.albedo_texture.resource_path
				var inward := (generated.global_position - artwork.global_position).normalized()
				if not _require(
					artwork.global_transform.basis.z.normalized().dot(inward) > 0.0,
					"Activity room %d has an artwork facing away from the room" % (kind + 1)
				):
					return false
				if not _require(
					texture_path.get_file().begins_with(expected_prefix),
					"Activity room %d uses artwork from the wrong gallery: %s" % [kind + 1, texture_path]
				):
					return false
		var original_source := load(EXPECTED_ACTIVITY_SCENE_PATHS[kind]).instantiate() as Node3D
		if not _require(
			source.transform.is_equal_approx(original_source.transform),
			"Activity room %d changes the authored common_area root transform" % (kind + 1)
		):
			original_source.free()
			return false
		original_source.free()
		activity.free()
	return true


func _collect_gallery_artworks(node: Node, artworks: Array[MeshInstance3D]) -> void:
	for child in node.get_children():
		var mesh_instance := child as MeshInstance3D
		if mesh_instance != null and mesh_instance.name.begins_with("GalleryArtwork_"):
			artworks.append(mesh_instance)
		_collect_gallery_artworks(child, artworks)


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
func _test_partial_dorm_and_eight_room_activity_boundaries() -> bool:
	var demo_nest := NEST_SCENE.instantiate() as ModularNest
	root.add_child(demo_nest)
	await _wait_frames(3)
	var demo_generated := demo_nest.get_node("Generated") as Node3D
	if not _require(demo_nest.bed_count == 32, "Editor demo defaults to fewer than the full eight-room layout"):
		return false
	if not _require(_count_named_children(demo_generated, "DormRoom_") == 8, "Editor demo does not preview eight dorm rooms"):
		return false
	var fill_light := demo_nest.get_node("CeilingFill") as DirectionalLight3D
	var fill_color := fill_light.light_color
	if not _require(
		maxf(fill_color.r, maxf(fill_color.g, fill_color.b)) - minf(fill_color.r, minf(fill_color.g, fill_color.b)) <= 0.1,
		"Colored global fill light still makes identical dorm walls appear as different colors"
	):
		return false
	if not _require(not fill_light.shadow_enabled, "Ceiling fill should not add global room shadows"):
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
		_count_named_children(full_generated, "CorridorMarbleVein_") == 0,
		"Corridor still contains narrow decorative vein strips"
	):
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


func _surface_is_flat(parent: Node3D, node_path: String) -> bool:
	var surface := parent.get_node(node_path) as MeshInstance3D
	var top_y := G.visual_bounds_in(surface, parent).end.y
	return top_y > 0.0 and top_y <= 0.001


func _dorm_mural_path(dorm: ModularDormRoom) -> String:
	var mural := dorm.get_node("Generated/DormMural") as MeshInstance3D
	var material := mural.material_override as StandardMaterial3D
	return material.albedo_texture.resource_path


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
