extends Node
## Disposable instancing of formal static prototypes. Add this helper to the tree,
## then bind after placement/material/light restoration. No scene integration here.
## Before Lab inspection call set_enabled(false), or restore_sources(paths) before
## resolving a selection: one GPU draw cannot highlight only one source node.
## Original Mesh (including LODs) stays shared, never flattened or duplicated.
## Culling and LOD selection are per MultiMesh, not per original source. Experimental
## 24-metre cells retain exact light sets; visual LOD transitions require Web QA.
## Static-source contract: restore_before_write(node, recursive) BEFORE changing
## local transforms, layers, materials/overlays, skin, render flags or instance data.
## Writers release ownership through the live helper registry, including subclasses.
## Node property-list/resource/visibility/tree signals still restore automatically;
## mesh replacement emits property_list_changed in 4.7. Child transform setters do
## NOT emit a signal: explicit writers are required, not inferred notifications.
## Parent transforms are watched once per parent; full source audits run on enable.
## Only natural_light_scale / emission_energy_multiplier change at runtime in these
## libraries; distinct equivalent materials monitor those values, shared ones do not.
## Formal library buffers are written only during assembly by
## glb_placement.bind_meshes / mesh_instance_groups.populate (which replace sources).
## Runtime writers in fountain_show / estate_platform_cycle use excluded meshes.
## All instance data and bounds come from the owning MultiMesh's CPU upload input;
## never use renderer readback (including during bind), or deep-compare in the poll.
## Local-light changes invalidate only overlapping receiver/caster groups. There
## is no automatic rebuild; unrelated groups remain active.
const OPAQUE := preload("res://nest/rendering/estate_opaque_batches.gd")
const LIGHTING := preload("res://nest/rendering/estate_lighting.gd")
const SHEEN_SHADER := "res://nest/furniture/shared/bedroom/m01_sheen.gdshader"
const CPU_BUFFER_META := &"nest_instance_buffer"
const CELL := 24.0
const MAX_CHUNK_TRIALS := 16
# Ten micrometres on the actual uploaded AABB, not an approximate containment
# predicate: float32 inverse/rotation/reflection roundtrips can shrink an endpoint.
const BOUNDS_PADDING := 0.00001
const LIVE_BATCHERS := &"estate_static_render_batches"
const LIBRARIES := [
	"res://nest/furniture/shared/bedroom/bed-shared.glb",
	"res://nest/furniture/shared/bedroom/bedroom-planters.glb",
	"res://nest/furniture/shared/main/main-planters.glb",
	"res://nest/courtyard/parts/forest/forest-foliage.glb",
	"res://nest/courtyard/parts/forest/forest-twigs.glb",
	"res://nest/courtyard/parts/shared/plant-library.glb",
	"res://nest/courtyard/parts/forest/pine-tree.glb",
]
const STATIC_OPAQUE_LIBRARIES := [
	"res://nest/buildings/main/central-building.glb",
	"res://nest/buildings/pod/pod-building.glb",
	"res://nest/courtyard/parts/ground/outdoor-lights.glb",
	"res://nest/courtyard/parts/shared/shore-stones.glb",
	"res://nest/furniture/shared/bedroom/bedroom-cabinet.glb",
	"res://nest/furniture/shared/bedroom/bedroom-desks.glb",
	"res://nest/furniture/shared/bedroom/bedroom-lamps.glb",
	"res://nest/furniture/shared/bedroom/bedroom-rug.glb",
	"res://nest/furniture/shared/main/main-frames.glb",
]
# Both geometry types inherit gi_lightmap_texel_scale. Do not also copy the
# deprecated gi_lightmap_scale alias, which quantizes the same underlying value.
const FLAGS := OPAQUE.FLAGS + ["gi_lightmap_texel_scale", "physics_interpolation_mode"]

# Only shared parent frames are read each frame; source properties are static
# between bind and their writer's explicit release. No per-source polling.
class ParentWatch:
	extends RefCounted
	var node: Node3D
	var transform: Transform3D
	var groups: Array[Dictionary] = []
	func _init(parent: Node3D) -> void:
		node = parent
		transform = parent.global_transform

class LightWatch:
	extends RefCounted
	var node: Light3D
	var transform: Transform3D
	var aabb: AABB
	var mask: int
	var shadow_mask: int
	func _init(item: Dictionary) -> void:
		node = item.node
		transform = item.transform
		aabb = item.aabb
		mask = item.mask
		shadow_mask = item.shadow_mask
	func matches() -> bool:
		return (node.global_transform == transform and node.get_aabb() == aabb
			and node.light_cull_mask == mask and node.shadow_caster_mask == shadow_mask)

var groups: Array[Dictionary] = []
var _estate: Node3D
var _world: World3D
var _estate_transform := Transform3D.IDENTITY
var _lights: Array[Dictionary] = []
var _enabled := true
var _valid_groups := 0
var _material_pairs := {}
var _parent_watches: Array[ParentWatch] = []
var _parents := {}
var _source_groups := {}
var _light_watches: Array[LightWatch] = []
var _pending_lights := {}

static func source_mesh(node: GeometryInstance3D) -> Mesh:
	if node is MeshInstance3D: return node.mesh
	if node is MultiMeshInstance3D and node.multimesh != null: return node.multimesh.mesh
	return null

static func source_material(node: GeometryInstance3D) -> Material:
	if node is MeshInstance3D: return node.get_active_material(0)
	if node.material_override != null: return node.material_override
	var mesh := source_mesh(node)
	return mesh.surface_get_material(0) if mesh != null and mesh.get_surface_count() > 0 else null

static func material_allowed(material: Material) -> bool:
	if material == null or material.next_pass != null: return false
	if material is ShaderMaterial:
		return material.shader != null and material.shader.resource_path in [OPAQUE.OPAQUE_SHADER, SHEEN_SHADER]
	if material is BaseMaterial3D:
		return (material.transparency in [BaseMaterial3D.TRANSPARENCY_DISABLED,
			BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR, BaseMaterial3D.TRANSPARENCY_ALPHA_HASH]
			and material.billboard_mode == BaseMaterial3D.BILLBOARD_DISABLED
			and not material.proximity_fade_enabled
			and material.distance_fade_mode == BaseMaterial3D.DISTANCE_FADE_DISABLED
			and not material.grow and not material.use_point_size
			and not material.uv1_triplanar and not material.uv2_triplanar)
	return false

func allowed(node: GeometryInstance3D) -> bool:
	var mesh := source_mesh(node) as ArrayMesh
	if mesh == null or mesh.get_surface_count() != 1 or mesh.get_blend_shape_count() != 0: return false
	var library := str(mesh.get_meta("nest_source_library", ""))
	var material := source_material(node)
	if library in STATIC_OPAQUE_LIBRARIES:
		# Keep movable leaves, render partitions and ordered transparency independent.
		if node.has_meta("source_surface"): return false
		if mesh.get_meta("nest_source_extras", {}).get("door_leaf", false) or node.get_meta("extras", {}).get("door_leaf", false): return false
		if material is BaseMaterial3D and material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED: return false
	elif library not in LIBRARIES:
		return false
	if mesh.resource_name.to_lower().contains("movingbedduvet"): return false
	if node.name.to_lower().contains("movingbedduvet"): return false
	if node.has_meta("estate_instance_batch") or node.get_script() != null: return false
	if mesh.surface_get_format(0) & (Mesh.ARRAY_FORMAT_BONES | Mesh.ARRAY_FORMAT_WEIGHTS): return false
	if mesh.surface_get_primitive_type(0) != Mesh.PRIMITIVE_TRIANGLES: return false
	if node is MeshInstance3D and node.skin != null: return false
	if not node.is_visible_in_tree() or node.layers == 0: return false
	if node.material_overlay != null or node.transparency != 0.0: return false
	if node.custom_aabb != AABB() or not node.global_transform.is_finite(): return false
	# A same-sign batch moves winding reversal to its draw node. Singular transforms,
	# HLOD parents, lightmap ownership and arbitrary shader state remain unsupported.
	if is_zero_approx(node.global_basis.determinant()): return false
	var ancestor: Node = node
	while ancestor != null:
		if ancestor is Node3D and not ancestor.visibility_parent.is_empty(): return false
		if ancestor is GeometryInstance3D:
			if ancestor.visibility_range_begin != 0.0 or ancestor.visibility_range_end != 0.0: return false
		ancestor = ancestor.get_parent()
	if node is MultiMeshInstance3D:
		var multi: MultiMesh = node.multimesh
		if multi.transform_format != MultiMesh.TRANSFORM_3D or multi.instance_count == 0: return false
		if multi.visible_instance_count == 0 or multi.custom_aabb != AABB(): return false
	return material_allowed(material)

static func _pairing_owner(node: Node) -> bool:
	return (node is ReflectionProbe or node is VoxelGI or node is LightmapGI or node is Decal
		or (node is Light3D and not node is DirectionalLight3D))

func _same_world(node: Node) -> bool:
	return node is Node3D and node.is_inside_tree() and node.get_world_3d() == _world

func _collect_lights() -> bool:
	_world = _estate.get_world_3d()
	# Include lights outside estate but inside its World3D; invisible day/night lights
	# also count, so toggling them cannot introduce a new pairing after batching.
	for node: Node in get_tree().root.find_children("*", "Node3D", true, false):
		if not _same_world(node) or not _pairing_owner(node): continue
		if not (node is OmniLight3D or node is SpotLight3D): return false
		var item := _light_snapshot(node as Light3D)
		_lights.append(item)
		_light_watches.append(LightWatch.new(item))
	return true

static func _light_snapshot(light: Light3D) -> Dictionary:
	var transform := light.global_transform
	var aabb := light.get_aabb()
	return {"node": light, "transform": transform, "aabb": aabb, "bounds": transform * aabb,
		"mask": light.light_cull_mask, "shadow_mask": light.shadow_caster_mask,
		"id": light.get_instance_id(), "omni": light is OmniLight3D}

func light_set(bounds: AABB, layers: int, _shadows: bool = false) -> PackedInt64Array:
	var result := PackedInt64Array()
	for item: Dictionary in _lights:
		if item.mask & layers and item.bounds.intersects(bounds):
			result.append(item.id)
	return result

func _within_light_budget(receivers: PackedInt64Array) -> bool:
	# GLES pairs Omni and Spot separately. Honor the configured limit (default 8),
	# retaining the helper's conservative total ceiling of 32 as well.
	if receivers.size() > 32: return false
	var limit := mini(32, int(ProjectSettings.get_setting("rendering/limits/opengl/max_lights_per_object", 8)))
	var omni := 0
	var spot := 0
	for item: Dictionary in _lights:
		if item.id not in receivers: continue
		if item.omni: omni += 1
		else: spot += 1
	return omni <= limit and spot <= limit

func _snapshot(node: GeometryInstance3D) -> Dictionary:
	var flags := []
	for property: String in FLAGS: flags.append(node.get(property))
	var relative := _estate_transform.affine_inverse() * node.global_transform
	var mesh := source_mesh(node)
	var local_bounds := mesh.get_aabb()
	var shadows := node.cast_shadow != GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var item := {"node": node, "parent": node.get_parent(), "mesh": mesh,
		"material": source_material(node), "override": node.material_override,
		"transform": node.global_transform, "relative": relative, "layers": node.layers,
		"flags": flags, "shadows": shadows, "mirrored": relative.basis.determinant() < 0.0,
		"path": str(node.get_meta("source_geometry_path", node.get_meta("v044_path", node.get_path()))),
		"multi": null, "count": 1, "visible_count": 1, "colors": false, "custom": false,
		"buffer": PackedFloat32Array(), "quality": MultiMesh.INTERP_QUALITY_FAST}
	if node is MultiMeshInstance3D:
		var multi: MultiMesh = node.multimesh
		item.multi = multi
		item.count = multi.instance_count
		item.visible_count = multi.visible_instance_count
		item.colors = multi.use_colors
		item.custom = multi.use_custom_data
		if not multi.has_meta(CPU_BUFFER_META): return {}
		var input: Variant = multi.get_meta(CPU_BUFFER_META)
		# Unknown upload provenance stays on its original draw. No GPU fallback.
		if not input is PackedFloat32Array: return {}
		item.buffer = input
		item.quality = multi.physics_interpolation_quality
		if not _valid_buffer(item): return {}
		var stride: int = 12 + (4 if item.colors else 0) + (4 if item.custom else 0)
		var mesh_bounds := mesh.get_aabb()
		for i in range(item.count):
			var instance_bounds := _buffer_transform(item.buffer, i * stride) * mesh_bounds
			local_bounds = instance_bounds if i == 0 else local_bounds.merge(instance_bounds)
	item.bounds = relative * local_bounds
	item.world_bounds = node.global_transform * local_bounds.grow(node.extra_cull_margin)
	item.lights = light_set(item.world_bounds, node.layers, shadows)
	return item

func bind(estate: Node3D) -> void:
	clear()
	if not is_inside_tree() or not estate.is_inside_tree(): return
	_estate = estate
	_estate_transform = estate.global_transform
	if not _estate_transform.is_finite() or _estate_transform.basis.determinant() <= 0.0: return
	if not _collect_lights(): return
	var candidates := {}
	var keyer := OPAQUE.new()
	for node: GeometryInstance3D in estate.find_children("*", "GeometryInstance3D", true, false):
		if not allowed(node): continue
		var item := _snapshot(node)
		if item.is_empty(): continue
		if not _within_light_budget(item.lights) or not _small(item.bounds): continue
		var center: Vector3 = item.bounds.get_center()
		var cell := Vector3i(floori(center.x / CELL), floori(center.y / CELL), floori(center.z / CELL))
		var key := _candidate_key(item, cell, keyer)
		if not candidates.has(key): candidates[key] = []
		candidates[key].append(item)
	keyer.free()
	for sources: Array in candidates.values():
		if sources.size() < 2: continue
		_create_group(sources)
	# Signal invalidation handles visibility/resource edits synchronously. Properties
	# without change signals are checked once immediately before rendering, after
	# actor/cloth updates (including late process/deferred work), also while paused.
	if not groups.is_empty():
		add_to_group(LIVE_BATCHERS)
		RenderingServer.frame_pre_draw.connect(poll)
		get_tree().node_added.connect(_node_added)
	print("ESTATE_INSTANCE_BATCHES ", statistics())

func _candidate_key(item: Dictionary, cell: Vector3i, keyer: OPAQUE) -> PackedByteArray:
	var owner_key: Array = [LIGHTING.lighting_group(item.node)]
	if item.material is BaseMaterial3D and item.material.emission_enabled:
		# Emission policy also uses the authored name and original energy metadata.
		owner_key.append(item.material.resource_name)
		owner_key.append(item.material.get_meta(LIGHTING.INITIAL_EMISSION, item.material.emission_energy_multiplier))
	return var_to_bytes([item.mesh.get_instance_id(), cell, item.layers, item.flags,
		keyer.material_key(item.material), owner_key, item.lights, item.mirrored,
		item.colors, item.custom, item.quality])

static func _small(bounds: AABB) -> bool:
	return bounds.size.x <= CELL and bounds.size.y <= CELL and bounds.size.z <= CELL

static func _valid_buffer(item: Dictionary) -> bool:
	var stride: int = 12 + (4 if item.colors else 0) + (4 if item.custom else 0)
	if item.buffer.size() != item.count * stride: return false
	for value: float in item.buffer:
		if not is_finite(value): return false
	for i in range(item.count):
		# Source MultiMesh local transforms must already be positive: the renderer
		# only knows its node's winding, not an individual instance's determinant.
		var transform := _buffer_transform(item.buffer, i * stride)
		if not transform.is_finite() or transform.basis.determinant() <= 0.0: return false
	return true

static func _buffer_transform(buffer: PackedFloat32Array, at: int) -> Transform3D:
	# RenderingServer's 3x4 rows store the basis transposed relative to Basis columns.
	return Transform3D(Basis(
		Vector3(buffer[at], buffer[at + 4], buffer[at + 8]),
		Vector3(buffer[at + 1], buffer[at + 5], buffer[at + 9]),
		Vector3(buffer[at + 2], buffer[at + 6], buffer[at + 10])),
		Vector3(buffer[at + 3], buffer[at + 7], buffer[at + 11]))

func _create_group(sources: Array) -> void:
	var geometry := _validated_bounds(sources)
	if not geometry.is_empty():
		_create_instances(sources, geometry)
		return
	# A wide union or a light in a gap must not discard compatible smaller sets.
	# First-fit over at most sixteen recent chunks bounds bind-time work. Failed
	# trials never mutate sources; unmatched singletons retain their original draw.
	var chunks: Array[Dictionary] = []
	for item: Dictionary in sources:
		var placed := false
		for i in range(maxi(0, chunks.size() - MAX_CHUNK_TRIALS), chunks.size()):
			var trial: Array = chunks[i].sources + [item]
			var candidate := _validated_bounds(trial)
			if candidate.is_empty(): continue
			chunks[i].sources = trial
			chunks[i].geometry = candidate
			placed = true
			break
		if not placed: chunks.append({"sources": [item], "geometry": {}})
	for chunk: Dictionary in chunks:
		if chunk.sources.size() > 1: _create_instances(chunk.sources, chunk.geometry)

func _validated_bounds(sources: Array) -> Dictionary:
	var first: Dictionary = sources[0]
	var bounds: AABB = first.bounds
	for item: Dictionary in sources:
		bounds = bounds.merge(item.bounds)
	if not _small(bounds): return {}
	var draw_transform := Transform3D.IDENTITY
	if first.mirrored: draw_transform.basis = Basis.from_scale(Vector3(-1, 1, 1))
	var draw_bounds := (draw_transform.affine_inverse() * bounds).grow(BOUNDS_PADDING)
	if not _small(draw_bounds): return {}
	# Test the actual generated AABB, including estate rotation and cull margin.
	# A union can encounter a light in a gap even when all original sets agree.
	var world_bounds := (_estate_transform * draw_transform) * draw_bounds.grow(first.node.extra_cull_margin)
	if light_set(world_bounds, first.layers, first.shadows) != first.lights: return {}
	# Shadow maps cull the union then rasterize the original triangles with the
	# original layers/cast_shadow. Different shadow-only sets need no equality or
	# receiver slots. Ensure the new caster AABB cannot drop an old caster pairing.
	for item: Dictionary in sources:
		if not world_bounds.encloses(item.world_bounds): return {}
	return {"transform": draw_transform, "bounds": draw_bounds, "world_bounds": world_bounds}

func _create_instances(sources: Array, geometry: Dictionary) -> void:
	var first: Dictionary = sources[0]
	var draw_transform: Transform3D = geometry.transform
	# Godot 4.7 RenderGeometryInstanceBase::set_transform takes the maximum
	# global basis column length for LOD; MultiMesh buffer scales do not enter it.
	# The union AABB cannot increase camera distance (orthographic distance=1),
	# so preserving the largest source scale*bias prevents a coarser LOD choice.
	var basis: Basis = (_estate_transform * draw_transform).basis
	var draw_scale := maxf(basis.x.length(), maxf(basis.y.length(), basis.z.length()))
	if not is_finite(draw_scale) or draw_scale <= 0.0: return
	var source_scale := draw_scale
	for item: Dictionary in sources:
		basis = item.transform.basis
		source_scale = maxf(source_scale, maxf(basis.x.length(), maxf(basis.y.length(), basis.z.length())))
	var lod_bias: float = first.flags[FLAGS.find("lod_bias")]
	var required_scale := PackedFloat32Array([source_scale * lod_bias])[0]
	if source_scale > draw_scale and lod_bias > 0.0:
		# Keep division and renderer float32 rounding on the finer-detail side.
		lod_bias *= (source_scale / draw_scale) * 1.000001
	lod_bias = PackedFloat32Array([lod_bias])[0]
	if not is_finite(lod_bias): return # Unrepresentable compensation retains original draws.
	if PackedFloat32Array([draw_scale * lod_bias])[0] < required_scale: return
	var draw_bounds: AABB = geometry.bounds
	var world_bounds: AABB = geometry.world_bounds
	var count := 0
	var visible_count := 0
	for item: Dictionary in sources:
		count += item.count
		visible_count += item.count if item.visible_count < 0 else item.visible_count
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.use_colors = first.colors
	multi.use_custom_data = first.custom
	multi.physics_interpolation_quality = first.quality
	multi.mesh = first.mesh
	multi.instance_count = count
	multi.visible_instance_count = visible_count
	multi.custom_aabb = draw_bounds
	var stride: int = 12 + (4 if first.colors else 0) + (4 if first.custom else 0)
	var upload := PackedFloat32Array()
	upload.resize(count * stride)
	var paths := PackedStringArray()
	var mapping := []
	var visible_index := 0
	var hidden_index := visible_count
	for item: Dictionary in sources:
		paths.append(item.path)
		var shown: int = item.count if item.visible_count < 0 else item.visible_count
		mapping.append({"source_geometry_path": item.path, "visible_start": visible_index,
			"visible_count": shown, "hidden_start": hidden_index, "hidden_count": item.count - shown})
		for i in range(item.count):
			var destination := visible_index if i < shown else hidden_index
			var at := destination * stride
			var transform: Transform3D = draw_transform.affine_inverse() * item.relative
			if item.multi != null:
				transform *= _buffer_transform(item.buffer, i * stride)
				# Preserve the canonical float channels, without renderer quantization.
				for component in range(12, stride): upload[at + component] = item.buffer[i * stride + component]
			upload[at] = transform.basis.x.x
			upload[at + 1] = transform.basis.y.x
			upload[at + 2] = transform.basis.z.x
			upload[at + 3] = transform.origin.x
			upload[at + 4] = transform.basis.x.y
			upload[at + 5] = transform.basis.y.y
			upload[at + 6] = transform.basis.z.y
			upload[at + 7] = transform.origin.y
			upload[at + 8] = transform.basis.x.z
			upload[at + 9] = transform.basis.y.z
			upload[at + 10] = transform.basis.z.z
			upload[at + 11] = transform.origin.z
			if i < shown: visible_index += 1
			else: hidden_index += 1
	# This exact array is both uploaded and retained for deterministic native checks.
	multi.buffer = upload
	multi.set_meta(CPU_BUFFER_META, upload)
	var draw := MultiMeshInstance3D.new()
	draw.name = "EstateInstanceBatch"
	draw.transform = draw_transform
	draw.multimesh = multi
	draw.material_override = first.material
	draw.layers = first.layers
	for i in range(FLAGS.size()): draw.set(FLAGS[i], first.flags[i])
	draw.lod_bias = lod_bias
	draw.set_meta("estate_instance_batch", true)
	draw.set_meta("source_geometry_path", paths[0])
	draw.set_meta("source_geometry_paths", paths)
	draw.set_meta("source_instance_ranges", mapping)
	_estate.add_child(draw)
	_register_group(sources, draw, world_bounds)

func _register_group(sources: Array, draw: GeometryInstance3D, world_bounds: AABB) -> void:
	# Caller owns geometry construction, bounds/pairing validation, render flags,
	# source-selection metadata and parenting. Registration is geometry-type agnostic.
	var first: Dictionary = sources[0]
	var group := {"sources": sources, "draw": draw, "valid": true, "active": false,
		"connections": [], "world_bounds": world_bounds}
	groups.append(group)
	_valid_groups += 1
	var invalidator := invalidate.bind(group)
	_connect(group, draw.tree_exiting, invalidator)
	var seen_parents := {}
	for item: Dictionary in sources:
		_source_groups[item.node.get_instance_id()] = group
		var parent: Node3D = item.node.get_parent_node_3d()
		if parent != null and parent != _estate and not seen_parents.has(parent):
			seen_parents[parent] = true
			if not _parents.has(parent):
				var watch := ParentWatch.new(parent)
				_parents[parent] = watch
				_parent_watches.append(watch)
			(_parents[parent] as ParentWatch).groups.append(group)
		if item.material != first.material:
			_watch_material_pair(first.material, item.material, group)
		_connect(group, item.node.visibility_changed, invalidator)
		_connect(group, item.node.tree_exiting, invalidator)
		_connect(group, item.node.property_list_changed, invalidator)
		_connect(group, item.mesh.changed, invalidator)
		_connect(group, item.material.changed, invalidator)
		_connect(group, item.material.property_list_changed, invalidator)
		if item.multi != null: _connect(group, item.multi.changed, invalidator)
		if item.material is ShaderMaterial: _connect(group, item.material.shader.changed, invalidator)
		# Drop the helper's temporary reference; the owning resource retains input.
		item.erase("buffer")
	activate(group, _enabled)

func _watch_material_pair(first: Material, other: Material, group: Dictionary) -> void:
	if not first is ShaderMaterial and not (first is BaseMaterial3D and first.emission_enabled): return
	var key := var_to_bytes([first.get_instance_id(), other.get_instance_id()])
	if not _material_pairs.has(key):
		_material_pairs[key] = {"first": first, "other": other, "groups": []}
	_material_pairs[key].groups.append(group)

func _poll_material_pairs() -> void:
	for pair: Dictionary in _material_pairs.values():
		var equal: bool
		if pair.first is ShaderMaterial:
			equal = pair.first.get_shader_parameter("natural_light_scale") == pair.other.get_shader_parameter("natural_light_scale")
		else:
			equal = pair.first.emission_energy_multiplier == pair.other.emission_energy_multiplier
		if not equal:
			for group: Dictionary in pair.groups: invalidate(group)

static func _connect(group: Dictionary, signal_value: Signal, callback: Callable) -> void:
	if signal_value.is_connected(callback): return
	signal_value.connect(callback)
	group.connections.append([signal_value, callback])

static func _disconnect(group: Dictionary) -> void:
	for connection: Array in group.connections:
		var signal_value: Signal = connection[0]
		if is_instance_valid(signal_value.get_object()) and signal_value.is_connected(connection[1]):
			signal_value.disconnect(connection[1])
	group.connections.clear()

func unchanged(item: Dictionary, active: bool, check_flags: bool = false) -> bool:
	if not is_instance_valid(item.node): return false
	var node := item.node as GeometryInstance3D
	if not is_instance_valid(node) or not node.is_inside_tree() or not node.is_visible_in_tree(): return false
	if node.get_parent() != item.parent or node.global_transform != item.transform: return false
	if node.layers != (0 if active else item.layers) or source_mesh(node) != item.mesh: return false
	if node.material_overlay != null or node.transparency != 0.0 or node.custom_aabb != AABB(): return false
	if node.material_override != item.override or source_material(node) != item.material: return false
	if node is MeshInstance3D and node.skin != null: return false
	if node.get_script() != null or not node.visibility_parent.is_empty(): return false
	# Flags are a static assembly contract, audited on re-enable, not every frame.
	if check_flags:
		for i in range(FLAGS.size()):
			if node.get(FLAGS[i]) != item.flags[i]: return false
	if node is MultiMeshInstance3D:
		var multi: MultiMesh = node.multimesh
		if multi != item.multi or multi.instance_count != item.count: return false
		if multi.visible_instance_count != item.visible_count or multi.custom_aabb != AABB(): return false
		if multi.transform_format != MultiMesh.TRANSFORM_3D: return false
		if multi.use_colors != item.colors or multi.use_custom_data != item.custom: return false
		if multi.physics_interpolation_quality != item.quality: return false
	return true

func activate(group: Dictionary, value: bool) -> void:
	if not is_instance_valid(group.draw): value = false
	var was_active: bool = group.active
	group.active = value
	if is_instance_valid(group.draw): group.draw.visible = value
	for item: Dictionary in group.sources:
		if not is_instance_valid(item.node): continue
		var node := item.node as GeometryInstance3D
		if value:
			node.layers = 0
			# Layer zero skips drawing, but leaves the instance in the renderer's
			# spatial index. Remove it from that index while the batch owns its draw.
			# Keep the Node3D visible for source selection and physics.
			RenderingServer.instance_set_visible(node.get_instance(), false)
		elif was_active:
			if node.layers == 0: node.layers = item.layers
			RenderingServer.instance_set_visible(node.get_instance(), node.is_visible_in_tree())

func invalidate(group: Dictionary) -> void:
	if not group.valid: return
	group.valid = false
	_valid_groups -= 1
	activate(group, false)
	_disconnect(group)

func _invalidate_all() -> void:
	for group: Dictionary in groups: invalidate(group)

func _node_added(node: Node) -> void:
	if node is OmniLight3D or node is SpotLight3D:
		# Arrival sets global_position after add_child(). Sample after setup, at the
		# next pre-draw poll, and wait for ready if a caller polls during construction.
		_pending_lights[node.get_instance_id()] = node
	elif _pairing_owner(node) and _same_world(node):
		_invalidate_all()

func _invalidate_light_groups(light: Dictionary) -> void:
	for group: Dictionary in groups:
		if not group.valid: continue
		var first: Dictionary = group.sources[0]
		var mask: int = light.mask | (light.shadow_mask if first.shadows else 0)
		if mask & first.layers and light.bounds.intersects(group.world_bounds): invalidate(group)

func _poll_lights() -> void:
	for i in range(_light_watches.size() - 1, -1, -1):
		var watch: LightWatch = _light_watches[i]
		if not is_instance_valid(watch.node) or not _same_world(watch.node):
			_invalidate_light_groups(_lights[i])
			_lights.remove_at(i)
			_light_watches.remove_at(i)
		elif not watch.matches():
			_invalidate_light_groups(_lights[i])
			var current := _light_snapshot(watch.node)
			_lights[i] = current
			_light_watches[i] = LightWatch.new(current)
			_invalidate_light_groups(current)
	if _pending_lights.is_empty(): return
	for identity: int in _pending_lights.keys():
		var node: Variant = _pending_lights[identity]
		if not is_instance_valid(node) or not _same_world(node):
			_pending_lights.erase(identity)
			continue
		if not node.is_node_ready(): continue
		_pending_lights.erase(identity)
		var known := false
		for item: Dictionary in _lights:
			if item.id == identity:
				known = true
				break
		if known: continue
		var current := _light_snapshot(node as Light3D)
		_lights.append(current)
		_light_watches.append(LightWatch.new(current))
		_invalidate_light_groups(current)

func poll() -> void:
	if not _enabled or _valid_groups == 0: return
	if not is_instance_valid(_estate) or not _estate.is_inside_tree():
		_invalidate_all()
		return
	if _estate.global_transform != _estate_transform:
		_invalidate_all()
		return
	_poll_lights()
	_poll_material_pairs()
	for watch: ParentWatch in _parent_watches:
		if not is_instance_valid(watch.node) or not watch.node.is_inside_tree() or watch.node.global_transform != watch.transform:
			for group: Dictionary in watch.groups: invalidate(group)

func set_enabled(value: bool) -> void:
	_enabled = value
	if value: poll()
	for group: Dictionary in groups:
		if value and group.valid:
			for item: Dictionary in group.sources:
				if not unchanged(item, group.active, true) or not material_allowed(item.material):
					invalidate(group)
					break
		activate(group, value and group.valid)

func statistics() -> Dictionary:
	var result := {"groups": 0, "sources": 0, "instances": 0, "multimesh_sources": 0,
		"parent_watches": _parent_watches.size()}
	for group: Dictionary in groups:
		if not group.valid: continue
		result.groups += 1
		for item: Dictionary in group.sources:
			result.sources += 1
			result.instances += item.count
			if item.multi != null: result.multimesh_sources += 1
	return result

func restore_sources(paths: PackedStringArray) -> void:
	# Call before selection lookup, so every existing source_geometry_path remains
	# drawable and existing Lab overlays/solo operate on the original nodes.
	for group: Dictionary in groups:
		for item: Dictionary in group.sources:
			if item.path in paths:
				invalidate(group)
				break

static func restore_before_write(node: Node, recursive: bool = false) -> void:
	# Runtime-only SceneTree membership, never serialized onto source assets. Both
	# surface and instance helpers register here; node identity avoids repeated-path
	# ambiguity between rooms. No helper exists yet during initial assembly.
	if not is_instance_valid(node) or not node.is_inside_tree(): return
	var helpers := node.get_tree().get_nodes_in_group(LIVE_BATCHERS)
	if helpers.is_empty(): return
	var targets: Array[Node] = [node]
	if recursive: targets.append_array(node.find_children("*", "GeometryInstance3D", true, false))
	for helper: Node in helpers:
		for target: Node in targets:
			helper._restore_node(target)

func _restore_node(node: Node) -> void:
	var group: Dictionary = _source_groups.get(node.get_instance_id(), {})
	if not group.is_empty(): invalidate(group)

func clear() -> void:
	_release_groups(false)

func _release_groups(defer_draw_deletion: bool) -> void:
	if is_in_group(LIVE_BATCHERS): remove_from_group(LIVE_BATCHERS)
	if RenderingServer.frame_pre_draw.is_connected(poll): RenderingServer.frame_pre_draw.disconnect(poll)
	if is_inside_tree() and get_tree().node_added.is_connected(_node_added):
		get_tree().node_added.disconnect(_node_added)
	for group: Dictionary in groups:
		_disconnect(group)
		activate(group, false)
		group.valid = false
		if is_instance_valid(group.draw):
			if defer_draw_deletion: group.draw.queue_free()
			else: group.draw.free()
	groups.clear()
	_valid_groups = 0
	_material_pairs.clear()
	_parent_watches.clear()
	_parents.clear()
	_source_groups.clear()
	_light_watches.clear()
	_pending_lights.clear()
	_lights.clear()
	_estate = null
	_world = null

func _exit_tree() -> void:
	# Estate can be locked while recursively exiting its children. Draws are our
	# siblings: restore/disconnect now, but never synchronously remove them here.
	# The estate frees them naturally on destruction; otherwise the queue does.
	_release_groups(true)
