extends "res://tools/pack_nest_assets.gd"
## Export evaluated worlds for camera-independent comparison. Never write assets.

const COMPARISON := "res://../build/nest-comparison/"
const FROZEN := {"estate/ElfieNest-complete-final.glb":"222810a8a4b0117855702f59acad18ebd3527b57c1b48322c7d25ad419f0903e", "estate/ElfieNest-complete-final.instances.bin":"18cd7a3718f1e1afb3edd239866bce8402bfe03be3ecc95f94be6b32026460de"}
const OMIT := ["resource_path", "resource_name", "resource_local_to_scene", "resource_scene_unique_id", "script", "owner", "name", "unique_name_in_owner", "scene_file_path", "editor_description", "process_mode", "process_priority", "process_physics_priority", "process_thread_group", "process_thread_group_order", "process_thread_messages", "physics_interpolation_mode", "transform", "position", "basis", "rotation", "rotation_degrees", "quaternion", "scale"]
const ATTRIBUTES := ["position", "normal", "tangent", "color", "uv", "uv2", "custom0", "custom1", "custom2", "custom3", "bones", "weights", "index"]
const DRAW_STATE := ["layers", "cast_shadow", "transparency", "extra_cull_margin", "ignore_occlusion_culling", "gi_mode", "visibility_range_begin", "visibility_range_end", "visibility_range_begin_margin", "visibility_range_end_margin", "visibility_range_fade_mode", "lod_bias", "sorting_offset", "sorting_use_aabb_center"]

var snap := {}
var snap_stream: FileAccess
var snap_meshes := {}
var snap_resources := {}
var snap_inputs := {}
var snap_errors: Array[String] = []

# Reuse the production review's fresh V044 evaluation, without constructing a PCK.
func add_file(_target: String, _source: String) -> bool:
	return true

func add_resource(_path: String) -> bool:
	return true

func pose(t: Transform3D) -> Array:
	return [t.basis.x.x,t.basis.x.y,t.basis.x.z,0.0,t.basis.y.x,t.basis.y.y,t.basis.y.z,0.0,t.basis.z.x,t.basis.z.y,t.basis.z.z,0.0,t.origin.x,t.origin.y,t.origin.z,1.0]

func blob(bytes: PackedByteArray, count: int, dtype: String) -> Dictionary:
	var at := snap_stream.get_position()
	snap_stream.store_buffer(bytes)
	var digest := HashingContext.new()
	digest.start(HashingContext.HASH_SHA256)
	if not bytes.is_empty(): digest.update(bytes)
	return {"offset":at,"bytes":bytes.size(),"count":count,"dtype":dtype,"sha256":digest.finish().hex_encode()}

func value(data: Variant) -> Variant:
	match typeof(data):
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING: return data
		TYPE_STRING_NAME, TYPE_NODE_PATH: return str(data)
		TYPE_VECTOR2: return [data.x,data.y]
		TYPE_VECTOR3: return [data.x,data.y,data.z]
		TYPE_VECTOR4: return [data.x,data.y,data.z,data.w]
		TYPE_VECTOR2I: return [data.x,data.y]
		TYPE_VECTOR3I: return [data.x,data.y,data.z]
		TYPE_COLOR: return [data.r,data.g,data.b,data.a]
		TYPE_QUATERNION: return [data.x,data.y,data.z,data.w]
		TYPE_TRANSFORM3D: return pose(data)
		TYPE_BASIS: return pose(Transform3D(data,Vector3.ZERO))
		TYPE_AABB: return [value(data.position),value(data.size)]
		TYPE_RECT2: return [value(data.position),value(data.size)]
		TYPE_PACKED_BYTE_ARRAY: return blob(data,data.size(),"u8")
		TYPE_PACKED_INT32_ARRAY: return blob(data.to_byte_array(),data.size(),"i32")
		TYPE_PACKED_FLOAT32_ARRAY: return blob(data.to_byte_array(),data.size(),"f32")
		TYPE_PACKED_VECTOR2_ARRAY: return blob(data.to_byte_array(),data.size(),"v2f32")
		TYPE_PACKED_VECTOR3_ARRAY: return blob(data.to_byte_array(),data.size(),"v3f32")
		TYPE_PACKED_COLOR_ARRAY: return blob(data.to_byte_array(),data.size(),"v4f32")
		TYPE_PACKED_VECTOR4_ARRAY: return blob(data.to_byte_array(),data.size(),"v4f32")
		TYPE_PACKED_FLOAT64_ARRAY: return blob(data.to_byte_array(),data.size(),"f64")
		TYPE_PACKED_INT64_ARRAY: return blob(data.to_byte_array(),data.size(),"i64")
		TYPE_PACKED_STRING_ARRAY: return Array(data)
		TYPE_ARRAY:
			var result := []
			for item: Variant in data: result.append(value(item))
			return result
		TYPE_DICTIONARY:
			var result := {}
			for key: Variant in data: result[str(key)] = value(data[key])
			return result
		TYPE_OBJECT:
			if data is Resource: return resource(data)
			if data == null: return null
	snap_errors.append("Unsupported stored value: " + type_string(typeof(data)))
	return {"unsupported":type_string(typeof(data))}

func properties(object: Object, selected: Array = []) -> Dictionary:
	var result := {}
	for prop: Dictionary in object.get_property_list():
		var key := str(prop.name)
		if not prop.usage & PROPERTY_USAGE_STORAGE or key in OMIT or key.begins_with("metadata/"): continue
		if not selected.is_empty() and key not in selected and not key.begins_with("instance_shader_parameters/"): continue
		result[key] = value(object.get(key))
	return result

func resource(object: Resource) -> Dictionary:
	var identity := object.get_instance_id()
	if snap_resources.has(identity): return {"resource":snap_resources[identity]}
	var id := str(snap_resources.size())
	snap_resources[identity] = id
	var record := {"type":object.get_class(),"source":object.resource_path}
	snap.resources[id] = record
	if object is Texture2D:
		var pixels: Image = object.get_image()
		if pixels == null or pixels.is_empty():
			snap_errors.append("Cannot read texture pixels: " + object.resource_path)
		else:
			if pixels.is_compressed():
				if pixels.decompress() != OK: snap_errors.append("Cannot decompress texture " + object.resource_path)
			if pixels.get_format() in [Image.FORMAT_L8,Image.FORMAT_LA8,Image.FORMAT_R8,Image.FORMAT_RG8,Image.FORMAT_RGB8,Image.FORMAT_RGBA8]: pixels.convert(Image.FORMAT_RGBA8)
			record.type = "Texture2D"
			record.image = {"width":pixels.get_width(),"height":pixels.get_height(),"format":pixels.get_format(),"mipmaps":pixels.has_mipmaps(),"pixels":blob(pixels.get_data(),pixels.get_data().size(),"u8")}
	elif object is Shader:
		record.code = object.code
		record.includes = {}
		var pending: Array[String] = [object.resource_path]
		while not pending.is_empty():
			var file: String = pending.pop_back()
			if file.is_empty() or record.includes.has(file): continue
			record.includes[file] = FileAccess.get_sha256(file)
			for dependency: String in dependencies(file):
				pending.append(dependency)
	elif object is Mesh:
		record.mesh = mesh(object)
	else:
		record.properties = properties(object)
	return {"resource":id}

func mesh(object: Mesh) -> String:
	var identity := object.get_instance_id()
	if snap_meshes.has(identity): return snap_meshes[identity]
	var id := str(snap_meshes.size())
	snap_meshes[identity] = id
	var surfaces := []
	if not (object is ArrayMesh or object is PrimitiveMesh): snap_errors.append("Unsupported mesh class: " + object.get_class())
	snap.meshes[id] = {"source":object.resource_path,"surfaces":surfaces,"aabb":value(object.get_aabb()),"blend_shapes":object.get_blend_shape_count() if object is ArrayMesh else 0}
	for surface: int in object.get_surface_count():
		var arrays := object.surface_get_arrays(surface)
		var stored := {}
		for slot: int in mini(arrays.size(),ATTRIBUTES.size()):
			if arrays[slot] != null and arrays[slot].size() > 0: stored[ATTRIBUTES[slot]] = value(arrays[slot])
		surfaces.append({"primitive":object.surface_get_primitive_type(surface) if object is ArrayMesh else Mesh.PRIMITIVE_TRIANGLES,"format":object.surface_get_format(surface) if object is ArrayMesh else null,"arrays":stored})
	return id

func owner_file(node: Node) -> String:
	var cursor := node
	while cursor != null:
		if cursor.has_method("bind_meshes") and cursor.library != null: return cursor.library.resource_path
		if not cursor.scene_file_path.is_empty(): return cursor.scene_file_path
		cursor = cursor.get_parent()
	return ""

func capture(world: Node3D, label: String) -> bool:
	snap = {"schema":1,"state":{"daylight":1.0,"water_time":0.0,"particles":"emitter definition; random mist hidden"},"engine":Engine.get_version_info(),"inputs":snap_inputs.duplicate(),"meshes":{},"resources":{},"placements":[],"lights":[],"environments":[],"particles":[],"errors":snap_errors}
	snap_meshes.clear()
	snap_resources.clear()
	snap_stream = FileAccess.open(COMPARISON + label + ".bin",FileAccess.WRITE)
	if not require(snap_stream != null,"Cannot open snapshot buffer"): return false
	var freezing := CONTROLLER.new()
	freezing.current = world
	freezing.freeze_water()
	freezing.free()
	for node: Node in world.find_children("*","",true,false):
		if node is MeshInstance3D or node is MultiMeshInstance3D:
			var geometry: Mesh = node.mesh if node is MeshInstance3D else (node.multimesh.mesh if node.multimesh != null else null)
			if geometry == null:
				snap_errors.append("Unbound geometry at " + str(world.get_path_to(node)))
				continue
			var bounds: AABB = node.global_transform * geometry.get_aabb()
			var record := {"kind":"mesh" if node is MeshInstance3D else "batch","path":str(node.get_meta("v044_path",world.get_path_to(node))),"node":str(world.get_path_to(node)),"file":owner_file(node),"mesh":mesh(geometry),"matrix":pose(node.global_transform),"visible":node.is_visible_in_tree(),"center":value(bounds.get_center()),"draw":properties(node,DRAW_STATE),"materials":[],"overlay":value(node.material_overlay)}
			for surface: int in geometry.get_surface_count():
				var material: Material = node.get_active_material(surface) if node is MeshInstance3D else (node.material_override if node.material_override != null else geometry.surface_get_material(surface))
				record.materials.append(value(material))
			if node is MultiMeshInstance3D:
				var batch: MultiMesh = node.multimesh
				record.batch = {"count":batch.instance_count,"visible":batch.visible_instance_count,"colors":batch.use_colors,"custom_data":batch.use_custom_data,"format":batch.transform_format,"buffer":value(batch.buffer),"aabb":value(batch.custom_aabb)}
			snap.placements.append(record)
		elif node is Light3D:
			snap.lights.append({"kind":node.get_class(),"path":str(node.get_meta("v044_path",world.get_path_to(node))),"matrix":pose(node.global_transform),"center":value(node.global_position),"visible":node.is_visible_in_tree(),"state":properties(node)})
		elif node is WorldEnvironment:
			snap.environments.append(properties(node))
		elif node is CPUParticles3D or node is GPUParticles3D:
			snap.particles.append({"kind":node.get_class(),"path":str(node.get_meta("v044_path",world.get_path_to(node))),"matrix":pose(node.global_transform),"center":value(node.global_position),"state":properties(node)})
	snap_stream.close()
	snap.buffer_sha256 = FileAccess.get_sha256(COMPARISON + label + ".bin")
	if not write(COMPARISON + label + ".json",JSON.stringify(snap,"  ",false,true)): return false
	print("NEST_SNAPSHOT ",label," placements=",snap.placements.size()," meshes=",snap.meshes.size()," resources=",snap.resources.size()," errors=",snap_errors.size())
	return true

func run() -> void:
	for frozen: String in FROZEN:
		if not require(FileAccess.get_sha256(NEST + frozen) == FROZEN[frozen], "Frozen V044 source changed: " + frozen): return
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(COMPARISON))
	var pending: Array[String] = [NEST + "nest.tscn",NEST + "estate/estate.tscn",NEST + "estate/estate_physics.gd",NEST + "estate/estate_lighting_sample.gd",NEST + "estate/estate_water_display.gd",NEST + "estate/ElfieNest-complete-final.glb",NEST + "estate/ElfieNest-complete-final.instances.bin",NEST + "assembly/asset-index.json",NEST + "assembly/glb_placement.gd", "res://tools/export_nest_comparison.gd", "res://tools/pack_nest_assets.gd", "res://tools/static_asset_review.gd", "res://project.godot"]
	var index: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(INDEX))
	for entry: Dictionary in index.fileGraph.entries.values():
		pending.append(NEST + str(entry.file))
	while not pending.is_empty():
		var file: String = pending.pop_back()
		if snap_inputs.has(file): continue
		if not require(FileAccess.file_exists(file), "Missing comparison input: " + file): return
		snap_inputs[file] = FileAccess.get_sha256(file)
		if FileAccess.file_exists(file + ".import"): snap_inputs[file + ".import"] = FileAccess.get_sha256(file + ".import")
		if file.get_extension() in ["glb","scn","tscn","tres","res","gd","gdshader","gdshaderinc","gltf"]:
			for dependency: String in dependencies(file):
				if dependency.begins_with("res://") and not dependency.begins_with("res://../build/"): pending.append(dependency)
	if not pack_reference(): return
	var original := (load(OUTPUT + "reference.scn") as PackedScene).instantiate() as Node3D
	root.add_child(original)
	if not capture(original,"reference"): return
	original.free()
	var assembled := (load(NEST + "assembly/estate.tscn") as PackedScene).instantiate() as Node3D
	root.add_child(assembled)
	if not capture(assembled,"reassembled"): return
	assembled.free()
	for file: String in snap_inputs:
		if FileAccess.get_sha256(file) != snap_inputs[file]: snap_errors.append("Source changed during export: " + file)
	# The reference JSON was written first; persist any late export failures in both.
	if not snap_errors.is_empty():
		for label: String in ["reference","reassembled"]:
			var document: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(COMPARISON + label + ".json"))
			document.errors = snap_errors
			write(COMPARISON + label + ".json", JSON.stringify(document,"  ",false,true))
	print("NEST_SNAPSHOT_EXPORT_COMPLETE errors=",snap_errors.size())
	quit(0 if snap_errors.is_empty() else 1)
