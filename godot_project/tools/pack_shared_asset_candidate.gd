extends "res://tools/pack_static_asset_review.gd"
## Build a separate review pack. Reuse native geometry only after a byte-level
## match, so the authoring interchange cannot change the V044 render inputs.

const CANDIDATE := "res://../build/godot-asset-migration/shared-v044-candidate/"
const BASELINE_PACK := "res://../build/components/godot-web/v044-assets.pck"
const POD_SCENE := BASE + "models/pod-building.scn"
const SHOWCASE_GAP := 0.18
var mesh_keys := {}
var canonical := {}
var seen_original := {}
var used_candidate := {}
var replacements := 0

func geometry_key(mesh: ArrayMesh) -> String:
	var identity := mesh.get_instance_id()
	if mesh_keys.has(identity): return mesh_keys[identity]
	var surfaces: Array = []
	for original: Dictionary in mesh.get("_surfaces"):
		var surface := original.duplicate()
		surface.erase("material")
		surface.erase("name")
		surfaces.append(surface)
	var key := digest([surfaces, mesh.custom_aabb, mesh.lightmap_size_hint,
		mesh.get("_blend_shape_names"), mesh.blend_shape_mode, mesh.shadow_mesh])
	mesh_keys[identity] = key
	return key

func eligible(node: MeshInstance3D) -> bool:
	return node.mesh is ArrayMesh and not node.mesh.resource_local_to_scene and node.mesh.get_script() == null

func remember_geometry(node: MeshInstance3D) -> void:
	if not eligible(node): return
	var key := geometry_key(node.mesh)
	if not canonical.has(key): canonical[key] = node.mesh

func reuse_geometry(node: MeshInstance3D, track_world := false) -> bool:
	if not eligible(node): return true
	var original := node.mesh as ArrayMesh
	var shared := canonical.get(geometry_key(original), original) as ArrayMesh
	if track_world: seen_original[original.get_instance_id()] = true
	if shared != original:
		var active: Array[Material] = []
		for i: int in original.get_surface_count():
			var material := node.get_active_material(i)
			# Null cannot override a non-null surface default. Preserve the
			# native variant if that difference cannot be expressed on the node.
			if material == null and shared.surface_get_material(i) != null:
				if track_world: used_candidate[original.get_instance_id()] = true
				return true
			active.append(material)
		node.mesh = shared
		for i: int in active.size():
			if node.get_active_material(i) != active[i]: node.set_surface_override_material(i, active[i])
			if node.get_active_material(i) != active[i]: return false
		if track_world: replacements += 1
	if track_world: used_candidate[node.mesh.get_instance_id()] = true
	return true

func copy_render_node(source: MeshInstance3D, parent: Node3D, name_for_part: String) -> MeshInstance3D:
	var copy := MeshInstance3D.new()
	copy.name = name_for_part
	for property: Dictionary in source.get_property_list():
		var key := str(property.name)
		if property.usage & PROPERTY_USAGE_STORAGE and key not in ["name", "owner", "script", "unique_name_in_owner"]:
			copy.set(key, source.get(key))
	copy.transform = source.global_transform
	parent.add_child(copy)
	copy.show()
	return copy

func prototype_bounds(group: Node3D) -> AABB:
	var bounds := AABB()
	for index: int in group.get_child_count():
		var part := group.get_child(index) as MeshInstance3D
		var box := group.transform * part.transform * part.get_aabb()
		bounds = box if index == 0 else bounds.merge(box)
	return bounds

func row_view(groups: Array, world: Node3D, front_row := false) -> Node3D:
	var result := Node3D.new()
	result.name = "Prototypes"
	var items: Array[Dictionary] = []
	for index: int in groups.size():
		var group := Node3D.new()
		group.name = "Prototype_%03d" % index
		result.add_child(group)
		for path: String in groups[index]:
			var original := world.get_node(NodePath(path)) as MeshInstance3D
			copy_render_node(original, group, "Part_%04d" % group.get_child_count())
		if front_row:
			var facing := (group.get_child(0) as Node3D).basis.z
			group.rotate_y(-atan2(facing.x, facing.z))
		items.append({"node": group, "bounds": prototype_bounds(group), "index": index})
	if front_row:
		result.set_meta("review_front_row", true)
		items.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
			var height_a: float = a.bounds.size.y
			var height_b: float = b.bounds.size.y
			return a.index < b.index if height_a == height_b else height_a < height_b
		)
	var x := 0.0
	var z := 0.0
	var row_depth := 0.0
	for index: int in items.size():
		var group: Node3D = items[index].node
		var bounds: AABB = items[index].bounds
		if front_row:
			group.position = Vector3(x, 0.0, -bounds.size.z * 0.5) - bounds.position
			x += bounds.size.x + SHOWCASE_GAP
			continue
		if index > 0 and index % 8 == 0:
			x = 0.0
			z += row_depth + 0.35
			row_depth = 0.0
		group.position = Vector3(x, 0.0, z) - bounds.position
		x += bounds.size.x + maxf(0.15, bounds.size.x * 0.18)
		row_depth = maxf(row_depth, bounds.size.z)
	return result

func create_pod(world: Node3D, plan: Dictionary) -> Dictionary:
	var parts: Dictionary = plan.pod_parts.M01
	var keys: Array = parts.keys()
	keys.sort()
	var anchor_key := ""
	for key: String in keys:
		if str(parts[key]).contains("continuous lower floor"):
			anchor_key = key
			break
	if not check(not anchor_key.is_empty(), "Missing shared pod anchor"): return {}
	var anchor := world.get_node(NodePath(parts[anchor_key])) as MeshInstance3D
	var origin := Transform3D(Basis.IDENTITY, anchor.global_position)
	var prototype := Node3D.new()
	prototype.name = "SharedPod"
	var names := {}
	for key: String in keys:
		var source := world.get_node(NodePath(parts[key])) as MeshInstance3D
		var part := copy_render_node(source, prototype, "Part_%02d" % prototype.get_child_count())
		part.transform = origin.affine_inverse() * source.global_transform
		names[key] = str(part.name)
	return {"prototype": prototype, "names": names, "anchor_key": anchor_key,
		"anchor_transform": anchor.global_transform, "origin": origin}

func assign_pod_placements(building: Node3D, world: Node3D, plan: Dictionary, pod: Dictionary, scene: PackedScene) -> bool:
	var parts: Dictionary = pod.names
	var modules: Array = plan.pod_parts.keys()
	modules.sort()
	for module: String in modules:
		var paths: Dictionary = plan.pod_parts[module]
		for source_path: String in paths.values():
			var copy := building.get_node_or_null(NodePath(source_path)) as MeshInstance3D
			if copy == null: return check(false, "Missing pod node in building layout: " + source_path)
			copy.mesh = null
		var instance := scene.instantiate() as Node3D
		instance.name = module
		building.add_child(instance)
		instance.owner = building
		building.set_editable_instance(instance, true)
		var target_anchor := world.get_node(NodePath(paths[pod.anchor_key])) as MeshInstance3D
		instance.transform = target_anchor.global_transform * pod.anchor_transform.affine_inverse() * pod.origin
		for key: String in parts:
			var target := world.get_node(NodePath(paths[key])) as MeshInstance3D
			var part := instance.get_node(NodePath(parts[key])) as MeshInstance3D
			if not check(part.mesh == target.mesh, "Pod native mesh differs at " + module + " " + str(target.name)): return false
			part.visible = target.visible
			part.layers = target.layers
			part.cast_shadow = target.cast_shadow
			for i: int in part.mesh.get_surface_count():
				part.set_surface_override_material(i, target.get_surface_override_material(i))
			part.material_override = target.material_override
			part.material_overlay = target.material_overlay
	return true

func verify_pod_layout(layout: PackedScene, world: Node3D, plan: Dictionary, pod: Dictionary) -> bool:
	var assembly := layout.instantiate() as Node3D
	root.add_child(assembly)
	var sample: MeshInstance3D
	var references: Array[MeshInstance3D] = []
	for module: String in plan.pod_parts:
		var instance := assembly.get_node_or_null(NodePath(module)) as Node3D
		if not check(instance != null and instance.scene_file_path == POD_SCENE, "Pod is not a saved scene reference: " + module):
			assembly.free()
			return false
		for key: String in pod.names:
			var target := world.get_node(NodePath(plan.pod_parts[module][key])) as MeshInstance3D
			var part := instance.get_node(NodePath(pod.names[key])) as MeshInstance3D
			if not check(part.mesh == target.mesh and part.global_transform.is_equal_approx(target.global_transform)
					and part.visible == target.visible and part.layers == target.layers and part.cast_shadow == target.cast_shadow,
					"Saved pod part changed: " + module + "/" + str(part.name)):
				assembly.free()
				return false
			for i: int in part.mesh.get_surface_count():
				if not check(part.get_active_material(i) == target.get_active_material(i), "Saved pod color changed: " + module + "/" + str(part.name)):
					assembly.free()
					return false
			if key == pod.anchor_key:
				sample = part if sample == null else sample
				references.append(part)
	var old := (sample.mesh as ArrayMesh).custom_aabb
	var changed := AABB(Vector3(8, 9, 10), Vector3.ONE)
	(sample.mesh as ArrayMesh).custom_aabb = changed
	var applied := 0
	for part: MeshInstance3D in references:
		if (part.mesh as ArrayMesh).custom_aabb == changed: applied += 1
	(sample.mesh as ArrayMesh).custom_aabb = old
	assembly.free()
	return check(applied == 8, "Editing one pod mesh did not reach all eight instances")

func add_review_scene(pack: PCKPacker, path: String, node: Node3D) -> bool:
	var output := CANDIDATE + path
	var scene := PackedScene.new()
	if not check(scene.pack(node) == OK and ResourceSaver.save(scene, output, ResourceSaver.FLAG_COMPRESS) == OK, "Cannot save candidate " + path): return false
	return add_file(pack, BASE + path, output)

func run() -> void:
	var controller := load("res://tools/static_asset_review.gd") as Script
	if not check(controller != null and controller.can_instantiate(), "Cannot compile review controller"): return
	var plan: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CANDIDATE + "assembly-plan.json"))
	if not check(plan.duplicate_mesh_records == 0 and FileAccess.get_sha256(SNAPSHOT) == plan.snapshot_sha256, "Missing verified prototype plan"): return
	if not check(ProjectSettings.load_resource_pack(BASELINE_PACK, false), "Cannot mount the preserved review pack"): return
	var world := (load(BASE + "reassembled.scn") as PackedScene).instantiate() as Node3D
	root.add_child(world)
	for row: Dictionary in plan.geometry.values():
		var source := world.get_node(NodePath(row.source_path)) as MeshInstance3D
		remember_geometry(source)
	for node: MeshInstance3D in world.find_children("*", "MeshInstance3D", true, false):
		remember_geometry(node)
		if not check(reuse_geometry(node, true), "Cannot preserve material: " + str(node.name)): return
	print("SHARED_NATIVE_WORLD changed=", replacements, " mesh_resources=", seen_original.size(), " -> ", used_candidate.size())

	var pack := PCKPacker.new()
	var pack_path := CANDIDATE + "v044-shared-assets.pck"
	if not check(not FileAccess.file_exists(pack_path), "Candidate pack already exists"): return
	if not check(pack.pck_start(pack_path) == OK, "Cannot start candidate pack"): return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(CANDIDATE + "models"))
	var pod := create_pod(world, plan)
	if pod.is_empty(): return
	assign_owners(pod.prototype, pod.prototype)
	if not add_review_scene(pack, "models/pod-building.scn", pod.prototype): return
	pod.prototype.free()
	var pod_scene := load(CANDIDATE + "models/pod-building.scn") as PackedScene
	pod_scene.take_over_path(POD_SCENE)
	if not add_review_scene(pack, "reassembled.scn", world): return

	for item: Dictionary in plan.views:
		var id: String = item.id
		if id == "pod-building": continue
		var model: Node3D
		if plan.showcase_groups.has(id):
			model = row_view(plan.showcase_groups[id], world)
			assign_owners(model, model)
		else:
			model = (load(BASE + "models/" + id + ".scn") as PackedScene).instantiate()
			for node: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
				if not check(reuse_geometry(node), "Cannot preserve material in view: " + id): return
			if id == "building-layout":
				if not assign_pod_placements(model, world, plan, pod, pod_scene): return
		if not add_review_scene(pack, "models/" + id + ".scn", model): return
		model.free()
		if id == "building-layout":
			var layout := load(CANDIDATE + "models/building-layout.scn") as PackedScene
			if not verify_pod_layout(layout, world, plan, pod): return
	print("SHARED_NATIVE_VIEWS checked=", plan.views.size(), " pod_instances=8")

	# Keep the original reference scene and its dependencies for the A/B.
	# The old pack and all old native/authoring files stay untouched.
	var native: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(EXPORTED.path_join("export-report.json")))
	var verification: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(EXPORTED.path_join("verification-report.json")))
	for path: String in verification.shader_dependencies:
		if not check(FileAccess.get_sha256(path) == verification.shader_dependencies[path], "Shader changed " + path): return
		if not add_file(pack, path, path): return
	var resources := DirAccess.get_files_at(ProjectSettings.globalize_path(STAGE.path_join("resources")))
	if not check(resources.size() == native.resources_saved, "Baseline resource pool incomplete"): return
	for name: String in resources:
		if not add_file(pack, BASE + "resources/" + name, STAGE.path_join("resources").path_join(name)): return
	for path: String in ["project.godot", "review.tscn"]:
		if not add_file(pack, "res://" + path, STAGE.path_join(path)): return
	if not add_file(pack, "res://.godot/global_script_class_cache.cfg", STAGE.path_join("empty-class-cache.cfg")): return
	if not add_file(pack, "res://review.gd", "res://tools/static_asset_review.gd"): return
	for path: String in ["reference.scn", "menu.json"]:
		if not add_file(pack, BASE + path, STAGE.path_join(path)): return
	if not check(pack.flush() == OK, "Cannot finish candidate pack"): return
	store_json(CANDIDATE + "review-report.json", {"passed": true, "assets": plan.views.size(),
		"pack_sha256": FileAccess.get_sha256(pack_path), "frozen_sha256": plan.snapshot_sha256,
		"original_native_mesh_resources": seen_original.size(), "candidate_native_mesh_resources": used_candidate.size(),
		"replaced_native_mesh_references": replacements, "pod_instances": 8,
		"pod_prototype_edit_reaches_all_instances": true,
		"scope": "Static review candidate with preserved original A/B resources, not a production bundle."})
	world.free()
	print("SHARED_REVIEW_READY ", pack_path)
	quit()
