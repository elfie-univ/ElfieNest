extends Node
## Disposable draw batches; source geometry, semantics and LODs stay authoritative.
const LIBRARIES := ["central-building.glb","pod-building.glb","shared-ground.glb","picnic.glb"]
const OPAQUE_SHADER := "res://nest/rendering/estate_opaque.gdshader"
const CELL := 16.0
const MAX_VERTICES := 32768
const FLAGS := ["cast_shadow","gi_mode","extra_cull_margin","ignore_occlusion_culling","lod_bias","sorting_offset","sorting_use_aabb_center","visibility_range_begin","visibility_range_end","visibility_range_begin_margin","visibility_range_end_margin","visibility_range_fade_mode"]
var groups: Array[Dictionary] = []
var _material_keys := {}
var _lights: Array[Light3D] = []
var _enabled := true

func material_key(material: Material) -> PackedByteArray:
	if _material_keys.has(material): return _material_keys[material]
	var values := [material.get_class()]
	for property: Dictionary in material.get_property_list():
		if not property.usage & PROPERTY_USAGE_STORAGE: continue
		var name := str(property.name)
		if name in ["resource_name","resource_path","resource_scene_unique_id"] or name.begins_with("metadata/"): continue
		values.append([name,material.get(name)])
	var result := var_to_bytes(values)
	_material_keys[material] = result
	return result

func allowed(node: MeshInstance3D) -> bool:
	var mesh := node.mesh as ArrayMesh
	if mesh == null or mesh.get_surface_count()!=1 or mesh.get_blend_shape_count()!=0 or node.skin!=null: return false
	if not node.is_visible_in_tree() or node.layers==0 or node.transparency!=0.0 or node.material_overlay!=null: return false
	if node.visibility_range_begin!=0.0 or node.visibility_range_end!=0.0: return false
	var extras: Dictionary = node.get_meta("extras",{})
	if extras.get("door_leaf",false) or extras.get("furniture",false): return false
	if not str(mesh.get_meta("nest_source_library","")).get_file() in LIBRARIES: return false
	var surface: Dictionary = mesh.get("_surfaces")[0]
	if surface.primitive!=Mesh.PRIMITIVE_TRIANGLES or surface.get("index_count",0)==0 or not surface.get("lods",[]).is_empty(): return false
	if surface.format & Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES or surface.get("skin_data",PackedByteArray()).size()>0: return false
	var material := node.get_active_material(0)
	if material == null or material.next_pass!=null: return false
	if material is ShaderMaterial:
		return material.shader!=null and material.shader.resource_path==OPAQUE_SHADER
	if material is BaseMaterial3D:
		return material.transparency==BaseMaterial3D.TRANSPARENCY_DISABLED and not material.emission_enabled and material.billboard_mode==BaseMaterial3D.BILLBOARD_DISABLED and not material.proximity_fade_enabled and material.distance_fade_mode==BaseMaterial3D.DISTANCE_FADE_DISABLED
	return false

func light_set(bounds: AABB, mask: int) -> PackedInt64Array:
	var result := PackedInt64Array()
	for light: Light3D in _lights:
		if not light.light_cull_mask & mask: continue
		var radius: float = light.omni_range if light is OmniLight3D else light.spot_range
		var extent := Vector3.ONE*radius
		if AABB(light.global_position-extent,extent*2.0).intersects(bounds): result.append(light.get_instance_id())
	return result

func bind(estate: Node3D) -> void:
	process_priority = 1000
	# Reflection-probe pairing is per geometry. Keep its original receivers intact.
	if not estate.find_children("*","ReflectionProbe",true,false).is_empty(): return
	for light: Light3D in estate.find_children("*","Light3D",true,false):
		if light is OmniLight3D or light is SpotLight3D: _lights.append(light)
	var candidates := {}
	for node: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		if not allowed(node): continue
		var bounds := node.global_transform*node.get_aabb()
		if bounds.size.length()>CELL*2.0: continue
		var center := bounds.get_center()
		var cell := Vector3i(floori(center.x/CELL),floori(center.y/CELL),floori(center.z/CELL))
		var flags := FLAGS.map(func(property: String) -> Variant: return node.get(property))
		var lights := light_set(bounds,node.layers)
		if lights.size()>32: continue
		var material := node.get_active_material(0)
		var surface: Dictionary = node.mesh.get("_surfaces")[0]
		var key := var_to_bytes([node.get_parent().get_instance_id(),node.global_transform,cell,node.layers,flags,surface.format,material_key(material),lights])
		if not candidates.has(key): candidates[key] = {"sources":[],"bounds":bounds,"lights":lights,"vertices":0}
		var candidate: Dictionary = candidates[key]
		if candidate.vertices+surface.vertex_count>MAX_VERTICES: continue
		candidate.vertices += surface.vertex_count
		candidate.bounds = candidate.bounds.merge(bounds)
		candidate.sources.append({"node":node,"mesh":node.mesh,"material":material,"transform":node.global_transform,"layers":node.layers,"flags":flags})
	for candidate: Dictionary in candidates.values():
		if candidate.sources.size()<2: continue
		var source: Dictionary = candidate.sources[0]
		if light_set(candidate.bounds,source.layers)!=candidate.lights: continue
		var draw := MeshInstance3D.new()
		draw.name = "OpaqueBatchDraw"
		draw.mesh = join(candidate.sources)
		if draw.mesh==null: continue
		draw.material_override = source.material
		draw.layers = source.layers
		for i in range(FLAGS.size()): draw.set(FLAGS[i],source.flags[i])
		draw.set_meta("source_geometry_path",str(source.node.get_meta("v044_path",source.node.name)))
		source.node.add_child(draw)
		var group := {"sources":candidate.sources,"draw":draw,"valid":true,"active":false}
		groups.append(group)
		var invalidator := invalidate.bind(group)
		for item: Dictionary in candidate.sources:
			if not item.mesh.changed.is_connected(invalidator):
				item.mesh.changed.connect(invalidator)
		activate(group,true)
	_material_keys.clear()
	print("OPAQUE_RENDER_BATCHES groups=",groups.size()," replaced=",groups.reduce(func(total: int, group: Dictionary) -> int: return total+group.sources.size(),0))

static func join(sources: Array) -> ArrayMesh:
	var first: Dictionary = sources[0].mesh.get("_surfaces")[0]
	var output := first.duplicate()
	var positions := PackedByteArray(); var normals := PackedByteArray(); var attributes := PackedByteArray()
	var indices := PackedInt32Array(); var vertices := 0
	var bounds: AABB = sources[0].mesh.get_aabb()
	for item: Dictionary in sources:
		var surface: Dictionary = item.mesh.get("_surfaces")[0]
		if surface.format!=first.format or not surface.get("lods",[]).is_empty(): return null
		var count: int = surface.vertex_count
		var stride := RenderingServer.mesh_surface_get_format_vertex_stride(surface.format,count)
		var normal_offset := RenderingServer.mesh_surface_get_format_offset(surface.format,count,Mesh.ARRAY_NORMAL)
		positions.append_array(surface.vertex_data.slice(0,count*stride))
		if surface.format & Mesh.ARRAY_FORMAT_NORMAL: normals.append_array(surface.vertex_data.slice(normal_offset))
		attributes.append_array(surface.get("attribute_data",PackedByteArray()))
		var bytes: PackedByteArray = surface.index_data
		var index_stride := 2 if count<=65536 else 4
		for i in range(surface.index_count): indices.append((bytes.decode_u16(i*2) if index_stride==2 else bytes.decode_u32(i*4))+vertices)
		vertices += count
		bounds = bounds.merge(item.mesh.get_aabb())
	positions.append_array(normals)
	var packed := PackedByteArray(); var stride := 2 if vertices<=65536 else 4
	packed.resize(indices.size()*stride)
	for i in range(indices.size()):
		if stride==2: packed.encode_u16(i*2,indices[i])
		else: packed.encode_u32(i*4,indices[i])
	output.vertex_data = positions; output.attribute_data = attributes; output.index_data = packed
	output.vertex_count = vertices; output.index_count = indices.size(); output.aabb = bounds
	var result := ArrayMesh.new(); result.set("_surfaces",[output]); result.custom_aabb = bounds
	return result

func unchanged(item: Dictionary, active: bool) -> bool:
	var node := item.node as MeshInstance3D
	return is_instance_valid(node) and node.is_visible_in_tree() and node.mesh==item.mesh and node.global_transform==item.transform and node.layers==(0 if active else item.layers) and node.get_active_material(0)==item.material and node.transparency==0.0 and node.material_overlay==null and FLAGS.map(func(property: String) -> Variant: return node.get(property))==item.flags

func activate(group: Dictionary, value: bool) -> void:
	if not is_instance_valid(group.draw): value = false
	group.active = value
	if is_instance_valid(group.draw): group.draw.visible = value
	for source: Dictionary in group.sources:
		if not is_instance_valid(source.node): continue
		if value: source.node.layers = 0
		elif source.node.layers==0: source.node.layers = source.layers

func invalidate(group: Dictionary) -> void:
	group.valid = false
	activate(group,false)

func set_enabled(value: bool) -> void:
	_enabled = value
	for group: Dictionary in groups:
		if value and group.valid and group.sources.all(func(item: Dictionary) -> bool: return unchanged(item,false)):
			activate(group,true)
		elif not value: activate(group,false)

func _process(_delta: float) -> void:
	if not _enabled: return
	for group: Dictionary in groups:
		if group.active and (not is_instance_valid(group.draw) or not group.sources.all(func(item: Dictionary) -> bool: return unchanged(item,true))): invalidate(group)

func _exit_tree() -> void:
	set_enabled(false)
