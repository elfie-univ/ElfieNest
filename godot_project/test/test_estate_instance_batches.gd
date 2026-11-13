extends SceneTree
## Synthetic fixtures only; the owner runs this script through the Godot guard.
const BATCHES := preload("res://nest/rendering/estate_instance_batches.gd")
const LIBRARY := "res://nest/furniture/shared/bedroom/bed-shared.glb"
var failures: Array[String] = []

func check(value: bool, message: String) -> void:
	if not value:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	call_deferred("run")

func test_native_properties() -> void:
	var material := StandardMaterial3D.new()
	check(BATCHES.material_allowed(material), "Default StandardMaterial3D uses valid native properties")
	material.grow = true
	check(not BATCHES.material_allowed(material), "Native grow property excludes displaced geometry")
	var source := MeshInstance3D.new()
	var draw := MultiMeshInstance3D.new()
	source.gi_lightmap_texel_scale = 2.5
	var source_properties := {}
	var draw_properties := {}
	for property: Dictionary in source.get_property_list(): source_properties[property.name] = true
	for property: Dictionary in draw.get_property_list(): draw_properties[property.name] = true
	for property: String in BATCHES.FLAGS:
		var supported: bool = source_properties.has(property) and draw_properties.has(property)
		check(supported, "Flag exists on MeshInstance3D and MultiMeshInstance3D: " + property)
		if not supported: continue
		draw.set(property, source.get(property))
		check(draw.get(property) == source.get(property), "Flag roundtrip preserves value: " + property)
	check(draw.gi_lightmap_texel_scale == 2.5, "Fractional texel density is not quantized through deprecated alias")
	source.free()
	draw.free()

func mesh_fixture() -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([
		Vector3.ZERO, Vector3(0.2, 0, 0), Vector3(0, 0.2, 0.2), Vector3(0.2, 0.2, 0.2)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP, Vector3.UP, Vector3.UP, Vector3.UP])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 1, 3, 2])
	var mesh := ArrayMesh.new()
	# A valid LOD must have fewer indices than the original surface.
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [],
		{4.0: PackedInt32Array([0, 1, 2])})
	mesh.surface_set_material(0, StandardMaterial3D.new())
	mesh.set_meta("nest_source_library", LIBRARY)
	return mesh

func fixture() -> Dictionary:
	var estate := Node3D.new()
	root.add_child(estate)
	var helper := BATCHES.new()
	estate.add_child(helper)
	var mesh := mesh_fixture()
	var sources: Array[MeshInstance3D] = []
	for i in range(2):
		var source := MeshInstance3D.new()
		source.mesh = mesh
		source.position = Vector3(1 + i, 1, 1)
		source.layers = 257
		source.set_meta("v044_path", "Bed/Part%d" % i)
		source.set_meta("extras", {"furniture": true, "piece": "bed_cover"})
		estate.add_child(source)
		sources.append(source)
	return {"estate": estate, "helper": helper, "mesh": mesh, "sources": sources}

func test_cleanup_lifecycle() -> void:
	for mode in ["clear", "helper_exit", "estate_detach", "estate_free"]:
		var f := fixture()
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == 1, "Cleanup fixture batches: " + mode)
		if f.helper.groups.is_empty():
			f.estate.free()
			continue
		var draw: MultiMeshInstance3D = f.helper.groups[0].draw
		match mode:
			"clear":
				f.helper.clear()
				check(not is_instance_valid(draw), "Explicit clear releases draw synchronously")
				check(f.helper.groups.is_empty(), "Explicit clear drops group references")
			"helper_exit":
				f.helper.free()
				check(is_instance_valid(draw) and draw.is_queued_for_deletion() and not draw.visible,
					"Helper exit hides and queues its sibling draw without removing it synchronously")
			"estate_detach":
				root.remove_child(f.estate)
				check(is_instance_valid(draw) and draw.is_queued_for_deletion() and not draw.visible,
					"Estate detachment does not mutate children during exit traversal")
			"estate_free":
				f.estate.free()
				check(not is_instance_valid(draw), "Estate owns final destruction of sibling draw")
				continue
		for source: MeshInstance3D in f.sources:
			check(source.layers == 257, "Cleanup restores surviving source layers: " + mode)
		f.estate.free()
		check(not is_instance_valid(draw), "Parent deletion safely consumes queued sibling: " + mode)

func report_transform_failure(source: Node3D, draw: MultiMeshInstance3D,
		index: int, expected_world: Transform3D) -> void:
	# Report the CPU input actually uploaded, not Dummy renderer readback.
	print("INSTANCE_TRANSFORM_DIAGNOSTIC ", {
		"source_global": source.global_transform,
		"draw_global": draw.global_transform,
		"expected_world": expected_world,
		"expected_relative": draw.global_transform.affine_inverse() * expected_world,
		"instance_index": index,
		"instance_transform": cpu_transform(draw.multimesh, index),
		"upload_buffer": draw.multimesh.get_meta("nest_instance_buffer"),
	})
	if source is MultiMeshInstance3D:
		print("INSTANCE_SOURCE_BUFFER ", source.multimesh.get_meta("nest_instance_buffer"))

func cpu_transform(multi: MultiMesh, index: int) -> Transform3D:
	var value: Variant = multi.get_meta("nest_instance_buffer", null)
	if not value is PackedFloat32Array:
		check(false, "MultiMesh must retain its actual CPU upload input")
		return Transform3D.IDENTITY
	var data: PackedFloat32Array = value
	var stride := 12 + (4 if multi.use_colors else 0) + (4 if multi.use_custom_data else 0)
	if data.size() != multi.instance_count * stride:
		check(false, "CPU upload has exactly one complete record per instance")
		return Transform3D.IDENTITY
	var at := index * stride
	var rows := Basis(Vector3(data[at], data[at + 1], data[at + 2]),
		Vector3(data[at + 4], data[at + 5], data[at + 6]),
		Vector3(data[at + 8], data[at + 9], data[at + 10]))
	return Transform3D(rows.transposed(), Vector3(data[at + 3], data[at + 7], data[at + 11]))

func test_mesh_and_selection() -> void:
	var f := fixture()
	f.estate.transform = Transform3D(Basis(Vector3.UP, 0.3), Vector3(9, 0, 3))
	var lods: Variant = f.mesh.get("_surfaces")[0].get("lods", [])
	check(not lods.is_empty(), "Fixture contains a real nonempty LOD")
	f.helper.bind(f.estate)
	check(f.helper.groups.size() == 1, "Identical material and Mesh resources are instanced")
	if not f.helper.groups.is_empty():
		var group: Dictionary = f.helper.groups[0]
		check(group.draw.multimesh.mesh == f.mesh, "The original Mesh identity is retained")
		check(f.mesh.get("_surfaces")[0].get("lods") == lods, "LOD data is untouched")
		check(group.draw.layers == 257 and group.draw.owner == null, "Generated draw keeps layers, has no scene owner")
		for i in range(2):
			check(f.sources[i].layers == 0 and f.sources[i].visible, "Only source render layers are hidden")
			check(group.world_bounds.encloses(f.sources[i].global_transform * f.mesh.get_aabb()),
				"Uploaded bounds strictly enclose original rotated source bounds")
			var world: Transform3D = group.draw.global_transform * cpu_transform(group.draw.multimesh, i)
			if not world.is_equal_approx(f.sources[i].global_transform):
				report_transform_failure(f.sources[i], group.draw, i, f.sources[i].global_transform)
			check(world.is_equal_approx(f.sources[i].global_transform), "Instance transform is relative to estate")
		check(group.draw.get_meta("source_geometry_paths").has("Bed/Part1"), "Every source selection path survives")
		f.helper.set_enabled(false)
		check(f.sources[0].layers == 257 and not group.draw.visible, "Disable restores original draws")
		f.helper.set_enabled(true)
		check(group.active, "Unchanged group can be enabled again")
		f.helper.restore_sources(PackedStringArray(["Bed/Part1"]))
		check(not group.active and f.sources[0].layers == 257, "Selecting any source restores the complete group")
	f.estate.free()

func test_lod_scale_compensation() -> void:
	# 4.7 GLES uses max(global basis column lengths) * lod_bias, not buffer scale.
	# Test the actual generated draw; no Dummy renderer LOD/buffer readback.
	for mode in ["scaled", "mirrored", "rotated", "estate_scaled", "multimesh", "local_only", "unit", "smaller", "zero_bias"]:
		var f := fixture()
		if mode == "estate_scaled": f.estate.basis = Basis.from_scale(Vector3(0.5, 2, 1))
		var sources: Array[GeometryInstance3D] = []
		for i in range(2):
			var source: GeometryInstance3D = f.sources[i]
			if mode in ["multimesh", "local_only"]:
				var multi := MultiMesh.new()
				multi.transform_format = MultiMesh.TRANSFORM_3D
				multi.mesh = f.mesh
				multi.instance_count = 1
				# Local scale is deliberately larger than node scale; it must not
				# be counted again when preserving the source renderer's LOD input.
				var input := PackedFloat32Array([4,0,0,0, 0,2,0,0, 0,0,1,0])
				multi.buffer = input
				multi.set_meta("nest_instance_buffer", input)
				var replacement := MultiMeshInstance3D.new()
				replacement.multimesh = multi
				replacement.transform = source.transform
				source.free()
				f.estate.add_child(replacement)
				source = replacement
			var scale := Vector3(2, 1, 1) if i == 0 else Vector3(1, 3, 1)
			if mode in ["unit", "local_only"]: scale = Vector3.ONE
			if mode == "smaller": scale = Vector3.ONE * 0.5
			if mode == "mirrored": scale.x = -scale.x
			source.basis = Basis.from_scale(scale)
			if mode == "rotated": source.basis = Basis(Vector3.UP, 0.37).scaled(scale)
			source.lod_bias = 0.0 if mode == "zero_bias" else 0.75
			sources.append(source)
		var original_lods: Variant = f.mesh.get("_surfaces")[0].get("lods")
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == 1, "LOD fixture forms one group: " + mode)
		if f.helper.groups.is_empty():
			f.estate.free()
			continue
		var draw: MultiMeshInstance3D = f.helper.groups[0].draw
		var basis: Basis = draw.global_basis
		var draw_scale := maxf(basis.x.length(), maxf(basis.y.length(), basis.z.length()))
		var effective := PackedFloat32Array([draw_scale * draw.lod_bias])[0]
		var largest := 0.0
		for i in range(sources.size()):
			var source: GeometryInstance3D = sources[i]
			basis = source.global_basis
			var source_scale := maxf(basis.x.length(), maxf(basis.y.length(), basis.z.length()))
			var before := PackedFloat32Array([source_scale * source.lod_bias])[0]
			largest = maxf(largest, before)
			# Orthographic cameras use distance=1 regardless of enlarged bounds.
			check(effective / 1.0 >= before / 1.0, "Orthographic LOD error never decreases: " + mode)
			var source_world := source.global_transform
			if source is MultiMeshInstance3D: source_world *= cpu_transform(source.multimesh, 0)
			check((draw.global_transform * cpu_transform(draw.multimesh, i)).is_equal_approx(source_world),
				"LOD compensation leaves uploaded world geometry unchanged: " + mode)
			var bounds: AABB = source_world * f.mesh.get_aabb()
			var batch_bounds: AABB = f.helper.groups[0].world_bounds
			for camera in [Vector3(30, 20, 40), Vector3(-30, -20, -40)]:
				var old_distance: float = Vector3.ZERO.max(bounds.position - camera).max(camera - bounds.end).length()
				var new_distance: float = Vector3.ZERO.max(batch_bounds.position - camera).max(camera - batch_bounds.end).length()
				check(effective / new_distance >= before / old_distance,
					"Perspective LOD error never decreases with actual union distance: " + mode)
		var uncompensated := draw_scale * sources[0].lod_bias
		if largest > uncompensated:
			# Fixture LOD edge_length=4. At this threshold the old batch chose
			# the coarse LOD, while the largest source kept full detail.
			var threshold := 4.0 * (largest + uncompensated) * 0.5
			check(4.0 * uncompensated <= threshold and 4.0 * largest > threshold,
				"Orthographic fixture exposes the original wrong LOD choice: " + mode)
			check(4.0 * effective > threshold, "Compensated draw retains the source's fine LOD: " + mode)
			check(effective <= largest * 1.00001, "Compensation is bounded to the largest source plus rounding guard")
		else:
			check(draw.lod_bias == sources[0].lod_bias, "No unnecessary bias change: " + mode)
		check(draw.multimesh.mesh == f.mesh and f.mesh.get("_surfaces")[0].get("lods") == original_lods,
			"LOD compensation preserves original mesh and index levels")
		f.helper.set_enabled(false)
		f.helper.set_enabled(true)
		check(f.helper.groups[0].active, "Compensated draw can be disabled and enabled")
		for source: GeometryInstance3D in sources:
			check(source.lod_bias == (0.0 if mode == "zero_bias" else 0.75), "Source LOD bias stays untouched")
		f.estate.free()

func test_rejections() -> void:
	for reason in ["identity", "material_value", "cell", "layers", "flags", "alpha", "overlay", "shader",
		"skin", "morph", "moving", "library", "mirror", "probe", "lightmap", "range"]:
		var f := fixture()
		var second: MeshInstance3D = f.sources[1]
		match reason:
			"identity": second.mesh = mesh_fixture()
			"material_value":
				second.material_override = f.mesh.surface_get_material(0).duplicate()
				second.material_override.roughness = 0.23
			"cell": second.position.x = BATCHES.CELL + 4.0
			"layers": second.layers = 1
			"flags": second.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			"alpha":
				var material := StandardMaterial3D.new()
				material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
				second.material_override = material
			"overlay": second.material_overlay = StandardMaterial3D.new()
			"shader":
				var material := ShaderMaterial.new()
				material.shader = Shader.new()
				material.shader.code = "shader_type spatial; void fragment() { ALBEDO = vec3(1.0); }"
				second.material_override = material
			"skin": second.skin = Skin.new()
			"morph":
				var mesh := ArrayMesh.new()
				mesh.add_blend_shape("moving")
				var arrays: Array = f.mesh.surface_get_arrays(0)
				var blend := []
				blend.resize(Mesh.ARRAY_MAX)
				blend[Mesh.ARRAY_VERTEX] = arrays[Mesh.ARRAY_VERTEX]
				blend[Mesh.ARRAY_NORMAL] = arrays[Mesh.ARRAY_NORMAL]
				mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [blend])
				mesh.set_meta("nest_source_library", LIBRARY)
				second.mesh = mesh
			"moving": second.mesh.resource_name = "MovingBedDuvet"
			"library": second.mesh.set_meta("nest_source_library", "res://other/bed-shared.glb")
			"mirror": second.scale.x = -1
			"probe": f.estate.add_child(ReflectionProbe.new())
			"lightmap": f.estate.add_child(LightmapGI.new())
			"range": second.visibility_range_end = 10
		f.helper.bind(f.estate)
		check(f.helper.groups.is_empty(), "Unsafe candidate rejected: " + reason)
		check(f.sources[0].layers == 257, "Rejected candidate leaves source untouched: " + reason)
		f.estate.free()
	for mode in [BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR, BaseMaterial3D.TRANSPARENCY_ALPHA_HASH]:
		var f := fixture()
		f.mesh.surface_get_material(0).transparency = mode
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == 1, "Cutout/hash material remains eligible")
		f.estate.free()

func test_invalidations() -> void:
	for change in ["mesh", "transform", "visible", "ancestor_visible", "material", "surface_material", "material_value", "overlay",
		"flags", "skin", "layers", "parent", "resource", "light", "added_light", "freed_draw"]:
		var f := fixture()
		var light := OmniLight3D.new()
		light.position = Vector3(1, 1, 1)
		f.estate.add_child(light)
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == 1, "Mutation fixture batches: " + change)
		if f.helper.groups.is_empty():
			f.estate.free()
			continue
		var group: Dictionary = f.helper.groups[0]
		var source: MeshInstance3D = f.sources[1]
		# Unsignaled static-node setters now require the same write barrier used by
		# production writers. Assert restoration BEFORE editing, not merely at poll.
		if change in ["transform", "material", "surface_material", "overlay", "skin", "layers"]:
			BATCHES.restore_before_write(source)
			check(not group.active and source.layers == 257, "Write barrier restores before static mutation: " + change)
		match change:
			"mesh": source.mesh = mesh_fixture()
			"transform": source.position.x += 0.1
			"visible": source.hide()
			"ancestor_visible": f.estate.hide()
			"material": source.material_override = StandardMaterial3D.new()
			"surface_material": source.set_surface_override_material(0, StandardMaterial3D.new())
			"material_value": f.mesh.surface_get_material(0).roughness = 0.23
			"overlay": source.material_overlay = StandardMaterial3D.new()
			"flags":
				f.helper.restore_sources(PackedStringArray(["Bed/Part1"]))
				source.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			"skin": source.skin = Skin.new()
			"layers": source.layers = 8
			"parent": f.estate.position.x += 0.1
			"resource": f.mesh.emit_changed()
			"light": light.omni_range += 1
			"added_light": f.estate.add_child(OmniLight3D.new())
			"freed_draw": group.draw.free()
		f.helper.poll()
		if change == "material_value":
			check(group.draw.material_override == f.mesh.surface_get_material(0), "Shared material parameters reach draw without deep comparison")
			f.estate.free()
			continue
		check(not group.valid and not group.active, "Mutation falls back before draw: " + change)
		check(f.sources[0].layers == 257, "Sibling drawing is restored: " + change)
		check(source.layers == (8 if change == "layers" else 257), "External layer change is preserved")
		f.helper.set_enabled(true)
		check(not group.active, "Invalid group cannot reactivate")
		f.estate.free()

func test_lights() -> void:
	for mode in ["different", "union", "padding", "limit", "same"]:
		var f := fixture()
		f.sources[1].position.x = 5
		for i in range(33 if mode == "limit" else 1):
			var light := OmniLight3D.new()
			light.position = Vector3(3 if mode == "union" else 1, 1, 1)
			light.omni_range = 10 if mode in ["same", "limit"] else 0.5
			if mode == "padding":
				# Outside the source bounds, inside only the uploaded rounding shell.
				light.position.x = 5.2 + light.omni_range + BATCHES.BOUNDS_PADDING * 0.5
			f.estate.add_child(light)
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == (1 if mode == "same" else 0), "Light pairing guard: " + mode)
		f.estate.free()
	# Shadow-only overlap may differ or exceed the receiving-light budget. Keeping
	# layers/cast_shadow and every triangle in the union preserves caster coverage.
	for mode in ["shadow_only", "shadow_gap", "mixed_limit", "default_limit"]:
		var f := fixture()
		f.sources[1].position.x = 5
		var setting := "rendering/limits/opengl/max_lights_per_object"
		var old_limit: Variant = ProjectSettings.get_setting(setting)
		if mode == "default_limit": ProjectSettings.set_setting(setting, 8)
		for i in range(40 if mode.begins_with("shadow") else 9):
			var light := SpotLight3D.new()
			light.position = Vector3(3 if mode == "shadow_gap" else 1, 1, 1.1 if mode.begins_with("shadow") else 3)
			light.spot_range = 0.5 if mode.begins_with("shadow") else 20.0
			light.light_cull_mask = 2 if mode.begins_with("shadow") else 257
			light.shadow_caster_mask = 257
			light.shadow_enabled = true
			f.estate.add_child(light)
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == (0 if mode == "default_limit" else 1),
			"Receiving budget excludes shadow-only lights: " + mode)
		if not f.helper.groups.is_empty():
			var draw: MultiMeshInstance3D = f.helper.groups[0].draw
			check(draw.layers == 257 and draw.cast_shadow == f.sources[0].cast_shadow,
				"Shadow caster layers and mode survive receiving/shadow separation")
			for source: MeshInstance3D in f.sources:
				check(f.helper.groups[0].world_bounds.encloses(source.global_transform * f.mesh.get_aabb()),
					"Generated shadow caster bounds cover every original triangle")
		ProjectSettings.set_setting(setting, old_limit)
		f.estate.free()

func test_equivalent_materials() -> void:
	for kind in ["base", "opaque", "sheen"]:
		for change in ["none", "input", "owner", "natural", "resource", "explicit"]:
			var f := fixture()
			var material: Material = StandardMaterial3D.new()
			if kind != "base":
				material = ShaderMaterial.new()
				(material as ShaderMaterial).shader = load("res://nest/furniture/shared/bedroom/m01_sheen.gdshader" if kind == "sheen" else "res://nest/rendering/estate_opaque.gdshader")
				(material as ShaderMaterial).set_shader_parameter("natural_light_scale", 1.0)
			f.mesh.surface_set_material(0, material)
			var other: Material = material.duplicate()
			other.resource_name = "Different label, identical rendering inputs"
			f.sources[1].material_override = other
			if change == "input":
				if kind == "base": (other as BaseMaterial3D).roughness = 0.17
				else: (other as ShaderMaterial).set_shader_parameter("natural_light_scale", 0.17)
			if change == "owner": f.sources[1].set_meta("extras", {"module": "M02"})
			f.helper.bind(f.estate)
			var expected: bool = change not in ["input", "owner"]
			check(f.helper.groups.size() == (1 if expected else 0), "Full material equivalence: " + kind + "/" + change)
			if expected and not f.helper.groups.is_empty():
				var group: Dictionary = f.helper.groups[0]
				check(group.draw.material_override == material, "Batch uses original material, without shader conversion")
				if change == "natural" and kind != "base":
					(material as ShaderMaterial).set_shader_parameter("natural_light_scale", 0.3)
					(other as ShaderMaterial).set_shader_parameter("natural_light_scale", 0.3)
					f.helper.poll()
					check(group.active, "Equal natural-light updates keep equivalent materials batched")
					(other as ShaderMaterial).set_shader_parameter("natural_light_scale", 0.2)
					f.helper.poll()
					check(not group.active, "Divergent natural-light inputs restore original materials")
				if change == "resource":
					other.emit_changed()
					check(not group.active, "Noncanonical material changed signal restores sources")
				if change == "explicit":
					f.helper.restore_sources(PackedStringArray(["Bed/Part1"]))
					check(not group.active, "Static parameter writer restores before unsignaled edits")
			f.estate.free()

func test_local_light_invalidation() -> void:
	for change in ["add", "move", "remove", "detach", "mask", "shadow_mask", "unrelated", "transient"]:
		var f := fixture()
		for x in [BATCHES.CELL * 2 + 1, BATCHES.CELL * 2 + 2, BATCHES.CELL * 4 + 1, BATCHES.CELL * 4 + 2]:
			var source := MeshInstance3D.new()
			source.mesh = f.mesh
			source.position = Vector3(x, 1, 1)
			source.layers = 257
			f.estate.add_child(source)
		var light := OmniLight3D.new()
		light.position = Vector3(1.5, 1, 1)
		light.omni_range = 2.0
		light.light_cull_mask = 2 if change in ["mask", "shadow_mask", "unrelated"] else 257
		light.shadow_caster_mask = 2
		if change not in ["add", "transient"]: f.estate.add_child(light)
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == 3, "Three independent cells batch before local light change: " + change)
		if f.helper.groups.size() != 3:
			if light.get_parent() == null: light.free()
			f.estate.free()
			continue
		var cells := {}
		for group: Dictionary in f.helper.groups:
			cells[floori(group.world_bounds.get_center().x / BATCHES.CELL)] = group
		match change:
			"add", "transient":
				f.estate.add_child(light)
				check(f.helper.statistics().groups == 3, "node_added defers sampling until light setup completes")
				light.position.x = BATCHES.CELL * 2 + 1.5
				if change == "transient": light.free()
			"move", "unrelated": light.position.x = BATCHES.CELL * 2 + 1.5
			"remove": light.free()
			"detach": f.estate.remove_child(light)
			"mask": light.light_cull_mask = 257
			"shadow_mask": light.shadow_caster_mask = 257
		f.helper.poll()
		var affects_old: bool = change in ["move", "remove", "detach", "mask", "shadow_mask"]
		var affects_new: bool = change in ["add", "move"]
		check(cells[0].active == (not affects_old), "Old light bounds invalidate only intersecting masks: " + change)
		check(cells[2].active == (not affects_new), "New light bounds invalidate only intersecting masks: " + change)
		check(cells[4].active, "Distant batch survives arrival light change: " + change)
		var remaining: int = f.helper.statistics().groups
		f.helper.poll()
		check(f.helper.statistics().groups == remaining, "Updated light snapshot is stable on the next poll")
		if change == "move":
			light.position.x = BATCHES.CELL * 4 + 1.5
			f.helper.poll()
			check(not cells[4].active, "A later move uses the updated snapshot and current bounds")
		if is_instance_valid(light) and light.get_parent() == null: light.free()
		f.estate.free()

func test_static_write_contract() -> void:
	var f := fixture()
	var other := fixture()
	var parent := Node3D.new()
	f.estate.add_child(parent)
	for source: MeshInstance3D in f.sources: source.reparent(parent)
	f.helper.bind(f.estate)
	other.helper.bind(other.estate)
	check(f.helper._parent_watches.size() == 1, "One shared parent watch replaces per-source transform reads")
	check(f.helper.groups.size() == 1 and other.helper.groups.size() == 1, "Independent estates batch")
	if not f.helper.groups.is_empty() and not other.helper.groups.is_empty():
		var group: Dictionary = f.helper.groups[0]
		BATCHES.restore_before_write(parent, true)
		check(not group.active and f.sources[0].layers == 257, "Subtree barrier restores before source setters")
		check(other.helper.groups[0].active, "Identical source paths in another estate are not restored")
		f.sources[0].position.x += 0.1
		f.helper.set_enabled(true)
		check(not group.active, "Released static group never silently reactivates")
	f.estate.free()
	other.estate.free()
	# Parent motion remains observable without any writer barrier.
	f = fixture()
	parent = Node3D.new()
	f.estate.add_child(parent)
	for source: MeshInstance3D in f.sources: source.reparent(parent)
	f.helper.bind(f.estate)
	parent.position.x += 0.1
	f.helper.poll()
	check(f.helper.statistics().groups == 0 and f.sources[0].layers == 257,
		"Shared parent motion restores its groups before drawing")
	f.estate.free()
	# The real cloth owner swaps a Mesh without changing the old Mesh resource.
	f = fixture()
	f.helper.bind(f.estate)
	var duvet := preload("res://runtime/actor/authored_duvet.gd").new()
	duvet.bind(f.sources[0])
	check(f.helper.statistics().groups == 0 and f.sources[1].layers == 257,
		"Authored duvet replacement restores by node property-list signal without poll")
	f.estate.free()

func test_material_writer() -> void:
	var f := fixture()
	var material := ShaderMaterial.new()
	material.shader = load("res://nest/furniture/shared/bedroom/m01_sheen.gdshader")
	f.mesh.surface_set_material(0, material)
	var optics := preload("res://nest/rendering/estate_lighting_sample.gd").new()
	optics.bind_m01(f.estate)
	f.helper.bind(f.estate)
	check(f.helper.groups.size() == 1, "Light-owner fixture batches shared sheen")
	if not f.helper.groups.is_empty():
		var group: Dictionary = f.helper.groups[0]
		var before: Material = f.sources[0].get_active_material(0)
		optics.set_opaque_shared(false)
		check(not group.active and f.sources[0].layers == 257, "Material rebinding restores without polling")
		check(f.sources[0].get_active_material(0) != before, "Comparison applies the requested independent material")
		optics.set_opaque_shared(true)
		check(f.sources[0].get_active_material(0) == before, "Comparison still restores the original shared material")
	f.estate.free()

func test_review_writer() -> void:
	var f := fixture()
	f.helper.bind(f.estate)
	var review := preload("res://tools/static_asset_review.gd").new()
	review.current = f.estate
	var matched: int = review.inspect_parts(["Bed/Part1"], false)
	check(matched == 1, "Review resolves a hidden batched source after restoring, before matching layers")
	check(f.helper.statistics().groups == 0 and f.sources[1].material_overlay == review.inspect_material,
		"Review overlay and source drawing take effect without poll")
	review.clear_inspection()
	check(f.sources[1].material_overlay == null, "Review cleanup retains original overlay behavior")
	review.free()
	f.estate.free()

func test_hot_rebind_writer() -> void:
	var f := fixture()
	var placement := Node3D.new()
	f.estate.add_child(placement)
	for source: MeshInstance3D in f.sources: source.reparent(placement)
	# Attach after entering the tree so this isolated fixture invokes bind_meshes
	# explicitly, with a complete in-memory PackedScene rather than import assets.
	placement.set_script(preload("res://nest/assembly/glb_placement.gd"))
	var prototype := Node3D.new()
	var part := MeshInstance3D.new()
	part.name = "Prototype"
	part.mesh = mesh_fixture()
	prototype.add_child(part)
	part.owner = prototype
	var library := PackedScene.new()
	check(library.pack(prototype) == OK, "Hot-rebind fixture packs")
	library.resource_path = "res://../build/godot_assets/runtime-fixes/in-memory-batch-fixture.tscn"
	placement.set("library", library)
	placement.set("source_nodes", PackedStringArray(["Prototype", "Prototype"]))
	f.helper.bind(f.estate)
	check(f.helper.groups.size() == 1, "Existing placements batch before hot rebind")
	var rebound: bool = placement.call("bind_meshes")
	check(rebound and f.helper.statistics().groups == 0, "Actual GLB rebinding releases previous batches")
	for source: MeshInstance3D in f.sources:
		check(source.layers == 257 and source.mesh != f.mesh, "Rebind preserves restored layers and installs replacement mesh")
	preload("res://nest/assembly/glb_placement.gd").cached_libraries.erase(library.resource_path)
	prototype.free()
	f.estate.free()

func test_mirrored_nodes() -> void:
	for mirrored in [false, true]:
		var f := fixture()
		f.estate.transform = Transform3D(Basis(Vector3.UP, 0.3), Vector3(9, 0, 3))
		for source: MeshInstance3D in f.sources:
			source.basis = Basis(Vector3.UP, 0.4).scaled(Vector3(-1.2 if mirrored else 1.2, 0.8, 1.1))
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == 1, "Same-sign source winding batches: " + str(mirrored))
		if not f.helper.groups.is_empty():
			var draw: MultiMeshInstance3D = f.helper.groups[0].draw
			check((draw.global_basis.determinant() < 0) == mirrored, "Renderer node owns winding reversal")
			for i in range(2):
				var local := cpu_transform(draw.multimesh, i)
				check(local.basis.determinant() > 0, "Uploaded local instances never carry a negative determinant")
				var before: Transform3D = f.sources[i].global_transform
				var after: Transform3D = draw.global_transform * local
				check(after.is_equal_approx(before), "Mirrored world transform is unchanged")
				var normal := Vector3(0.3, 0.5, 0.8).normalized()
				check((after.basis.inverse().transposed() * normal).is_equal_approx(before.basis.inverse().transposed() * normal),
					"Inverse-transpose normal transform is unchanged")
				var before_face := (before.basis * Vector3.RIGHT).cross(before.basis * Vector3.UP)
				var after_face := (after.basis * Vector3.RIGHT).cross(after.basis * Vector3.UP)
				check(after_face.is_equal_approx(before_face), "Front/back geometric orientation is unchanged")
		f.estate.free()

func test_multimeshes() -> void:
	for change in ["none", "mirrored", "partial", "missing_input", "bad_stride", "negative_local", "transform", "color", "custom", "count", "visible_count", "replace"]:
		var f := fixture()
		for source: Node in f.sources: source.free()
		var sources: Array[MultiMeshInstance3D] = []
		for n in range(2):
			var node := MultiMeshInstance3D.new()
			node.position = Vector3(1 + n, 1, 1)
			if change == "mirrored": node.scale.x = -1
			var multi := MultiMesh.new()
			multi.transform_format = MultiMesh.TRANSFORM_3D
			multi.use_colors = true
			multi.use_custom_data = true
			multi.mesh = f.mesh
			multi.instance_count = 2
			if change == "partial": multi.visible_instance_count = 1
			var input := PackedFloat32Array()
			for i in range(2):
				# Explicit row-major source data; rotation catches transposed packing.
				input.append_array(PackedFloat32Array([
					0.6,0,0.8,0, 0,1,0,0, -0.8,0,0.6,i,
					0.2 + n * 0.1,0.4,0.6,1, 0.5,0.25 + i * 0.1,0.75,1]))
			if n == 1 and change == "negative_local":
				for component in range(3): input[component] = -input[component]
			multi.buffer = input
			multi.set_meta("nest_instance_buffer", input)
			if n == 1 and change == "missing_input": multi.remove_meta("nest_instance_buffer")
			if n == 1 and change == "bad_stride":
				multi.set_meta("nest_instance_buffer", input.slice(0, input.size() - 1))
			node.multimesh = multi
			node.set_meta("source_geometry_path", "Plants/%d" % n)
			f.estate.add_child(node)
			sources.append(node)
		f.helper.bind(f.estate)
		if change in ["missing_input", "bad_stride", "negative_local"]:
			check(f.helper.groups.is_empty(), "Unknown or malformed CPU input stays unbatched: " + change)
			check(sources[0].layers == 1 and sources[1].layers == 1, "Rejected CPU input preserves original drawing")
			f.estate.free()
			continue
		check(f.helper.groups.size() == 1, "Existing MultiMeshes coalesce: " + change)
		if f.helper.groups.is_empty():
			f.estate.free()
			continue
		var group: Dictionary = f.helper.groups[0]
		var output: MultiMesh = group.draw.multimesh
		check((group.draw.global_basis.determinant() < 0) == (change == "mirrored"), "MultiMesh source node winding survives coalescing")
		check(output.instance_count == 4 and output.mesh == f.mesh, "All instances share the original mesh")
		check(output.visible_instance_count == (2 if change == "partial" else 4), "Visible prefix counts survive coalescing")
		var output_buffer: PackedFloat32Array = output.get_meta("nest_instance_buffer")
		check(output_buffer.size() == 80, "Four full transform/color/custom records are uploaded")
		var expected_bounds := AABB()
		for n in range(2):
			var source_buffer: PackedFloat32Array = sources[n].multimesh.get_meta("nest_instance_buffer")
			for i in range(2):
				var index := n + i * 2 if change == "partial" else n * 2 + i
				var authored := Transform3D(Basis(Vector3(0.6, 0, -0.8), Vector3.UP,
					Vector3(0.8, 0, 0.6)), Vector3(0, 0, i))
				check(cpu_transform(sources[n].multimesh, i).is_equal_approx(authored), "CPU source fixture retains its authored transform")
				var before: Transform3D = sources[n].global_transform * authored
				var after: Transform3D = group.draw.global_transform * cpu_transform(output, index)
				check(cpu_transform(output, index).basis.determinant() > 0, "Coalesced MultiMesh local determinant stays positive")
				var instance_bounds: AABB = (sources[n].transform * authored) * f.mesh.get_aabb()
				expected_bounds = instance_bounds if n == 0 and i == 0 else expected_bounds.merge(instance_bounds)
				if not before.is_equal_approx(after):
					report_transform_failure(sources[n], group.draw, index, before)
				check(before.is_equal_approx(after), "MultiMesh world transform retained")
				check(output_buffer.slice(index * 20 + 12, index * 20 + 16) == source_buffer.slice(i * 20 + 12, i * 20 + 16), "Color retained exactly in CPU upload")
				check(output_buffer.slice(index * 20 + 16, index * 20 + 20) == source_buffer.slice(i * 20 + 16, i * 20 + 20), "Custom data retained exactly in CPU upload")
		expected_bounds = (group.draw.transform.affine_inverse() * expected_bounds).grow(BATCHES.BOUNDS_PADDING)
		check(output.custom_aabb.position.is_equal_approx(expected_bounds.position)
			and output.custom_aabb.size.is_equal_approx(expected_bounds.size),
			"Uploaded bounds equal the authored CPU union plus the fixed rounding shell")
		var actual_world_bounds: AABB = group.draw.global_transform * output.custom_aabb
		check(actual_world_bounds == group.world_bounds, "Light pairing uses the actual uploaded expanded bounds")
		for item: Dictionary in group.sources:
			check(actual_world_bounds.encloses(item.world_bounds),
				"Uploaded bounds strictly preserve every source caster bound, including mirrored sources")
		var original: MultiMesh = sources[1].multimesh
		if change in ["transform", "color", "custom", "count", "visible_count", "replace"]:
			# Static-library writers explicitly release ownership before editing.
			BATCHES.restore_before_write(sources[1])
			check(not group.active, "MultiMesh write barrier restores before editing: " + change)
		match change:
			"transform": original.set_instance_transform(0, Transform3D.IDENTITY)
			"color": original.set_instance_color(0, Color.RED)
			"custom": original.set_instance_custom_data(0, Color.GREEN)
			"count": original.instance_count = 1
			"visible_count": original.visible_instance_count = 1
			"replace": sources[1].multimesh = MultiMesh.new()
		f.helper.poll()
		check(group.active == (change in ["none", "mirrored", "partial"]), "MultiMesh mutation detection: " + change)
		f.helper.clear()
		check(sources[0].layers == 1 and sources[1].layers == 1, "Clear restores MultiMesh sources")
		check(f.helper.groups.is_empty(), "Clear discards disposable draw groups")
		f.estate.free()

func test_large_multimesh_chunks() -> void:
	for mode in ["large", "extent_split", "light_split", "over_limit"]:
		var f := fixture()
		for source: Node in f.sources: source.free()
		f.mesh.set_meta("nest_source_library", "res://nest/courtyard/parts/forest/forest-foliage.glb")
		var lods: Variant = f.mesh.get("_surfaces")[0].get("lods")
		var span: float = BATCHES.CELL * 0.6
		var positions: Array = [2.0, 3.0]
		if mode == "extent_split": positions = [-BATCHES.CELL * 0.2, BATCHES.CELL * 0.6, -BATCHES.CELL * 0.2 + 1.0]
		if mode == "over_limit": span = BATCHES.CELL + 1.0
		if mode == "light_split":
			span = 0.4
			positions = [1.0, 5.0, 1.5]
			var light := OmniLight3D.new()
			light.position = Vector3(3, 1, 1)
			light.omni_range = 0.25
			f.estate.add_child(light)
		var nodes: Array[MultiMeshInstance3D] = []
		for x: float in positions:
			var source := MultiMeshInstance3D.new()
			source.position = Vector3(x, 1, 1)
			var multi := MultiMesh.new()
			multi.transform_format = MultiMesh.TRANSFORM_3D
			multi.mesh = f.mesh
			multi.instance_count = 2
			var input := PackedFloat32Array([1,0,0,0, 0,1,0,0, 0,0,1,0,
				1,0,0,span, 0,1,0,0, 0,0,1,0])
			multi.buffer = input
			multi.set_meta("nest_instance_buffer", input)
			source.multimesh = multi
			f.estate.add_child(source)
			nodes.append(source)
		f.helper.bind(f.estate)
		check(f.helper.groups.size() == (0 if mode == "over_limit" else 1), "Conservative chunk formation: " + mode)
		if not f.helper.groups.is_empty():
			var group: Dictionary = f.helper.groups[0]
			var draw: MultiMeshInstance3D = group.draw
			check(group.sources.size() == 2 and draw.multimesh.instance_count == 4, "Compatible pair survives an incompatible third source")
			check(draw.multimesh.mesh == f.mesh and f.mesh.get("_surfaces")[0].get("lods") == lods,
				"Large existing batches retain the exact original mesh and LOD indices")
			check(BATCHES._small(draw.multimesh.custom_aabb), "Uploaded padded chunk never exceeds CELL")
			if mode in ["large", "extent_split"]:
				check(draw.multimesh.custom_aabb.size.x > 8.0, "Fixture exercises batches rejected by the old eight-metre limit")
			for n in range(group.sources.size()):
				var item: Dictionary = group.sources[n]
				check(group.world_bounds.encloses(item.world_bounds), "Chunk retains exact source caster coverage")
				check(f.helper.light_set(group.world_bounds, item.layers) == item.lights, "Chunk adds no receiver lights")
				for i in range(2):
					var before: Transform3D = item.node.global_transform * cpu_transform(item.multi, i)
					var after: Transform3D = draw.global_transform * cpu_transform(draw.multimesh, n * 2 + i)
					check(before.is_equal_approx(after), "Large source CPU instance transforms are unchanged")
			if mode in ["extent_split", "light_split"]:
				check(nodes[0].layers == 0 and nodes[2].layers == 0 and nodes[1].layers == 1,
					"Greedy chunks keep the later compatible source and leave the singleton on its original draw")
		if mode == "over_limit":
			for source: MultiMeshInstance3D in nodes: check(source.layers == 1, "Oversize originals remain untouched")
		f.estate.free()

func run() -> void:
	test_native_properties()
	test_cleanup_lifecycle()
	test_mesh_and_selection()
	test_lod_scale_compensation()
	test_rejections()
	test_invalidations()
	test_lights()
	test_equivalent_materials()
	test_local_light_invalidation()
	test_static_write_contract()
	test_material_writer()
	test_review_writer()
	test_hot_rebind_writer()
	test_mirrored_nodes()
	test_multimeshes()
	test_large_multimesh_chunks()
	print("ESTATE_INSTANCE_BATCHES failures=", failures.size())
	quit(0 if failures.is_empty() else 1)
