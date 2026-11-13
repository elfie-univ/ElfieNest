extends "res://nest/rendering/estate_instance_batches.gd"
## Same-frame static pieces share a draw without welding or re-triangulation.
## Original meshes remain selectable and are restored by the inherited watchers.
## LODs reuse authored index buffers. A union AABB is no farther from the camera
## than any source AABB, so the selected detail is the original level or finer.
## At most eight union thresholds bound index memory; skipping thresholds retains
## finer geometry longer, never invents a coarser mesh. Dynamic cloth replacement
## restores its whole small group before drawing via the inherited mesh watches.
const SURFACE_LIBRARIES := ["bed-shared.glb", "bedroom-planters.glb"]
const MAX_JOIN_VERTICES := 262144
const MAX_SURFACE_EXTENT := 8.0
var _joined_meshes := {}

func bind(estate: Node3D) -> void:
 _joined_meshes.clear()
 super.bind(estate)

func allowed(node: GeometryInstance3D) -> bool:
 if not node is MeshInstance3D or not super.allowed(node): return false
 if str(node.mesh.get_meta("nest_source_library", "")).get_file() not in SURFACE_LIBRARIES: return false
 var surface: Dictionary = node.mesh.get("_surfaces")[0]
 return (surface.get("index_count",0)>0 and not surface.format & Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES
  and surface.get("skin_data",PackedByteArray()).is_empty())

func _candidate_key(item: Dictionary, _cell: Vector3i, keyer: OPAQUE) -> PackedByteArray:
 var surface: Dictionary = item.mesh.get("_surfaces")[0]
 return var_to_bytes([item.parent.get_instance_id(),item.transform,item.layers,item.flags,
  keyer.material_key(item.material),LIGHTING.lighting_group(item.node),item.lights,
  surface.format,surface.get("uv_scale",Vector4.ZERO)])

func _create_group(sources: Array) -> void:
 var first: Dictionary = sources[0]
 var bounds: AABB = first.mesh.get_aabb()
 var mesh_ids := PackedInt64Array()
 var vertices := 0
 for item: Dictionary in sources:
  bounds = bounds.merge(item.mesh.get_aabb())
  mesh_ids.append(item.mesh.get_instance_id())
  vertices += item.mesh.surface_get_array_len(0)
 if vertices > MAX_JOIN_VERTICES: return
 bounds = bounds.grow(BOUNDS_PADDING)
 var world_bounds: AABB = first.transform * bounds.grow(first.node.extra_cull_margin)
 var extent: Vector3 = (_estate_transform.affine_inverse() * world_bounds).size
 if extent.x > MAX_SURFACE_EXTENT or extent.y > MAX_SURFACE_EXTENT or extent.z > MAX_SURFACE_EXTENT: return
 if light_set(world_bounds,first.layers) != first.lights: return
 for item: Dictionary in sources:
  if not world_bounds.encloses(item.world_bounds): return
 var key := var_to_bytes(mesh_ids)
 if not _joined_meshes.has(key): _joined_meshes[key] = join(sources)
 var mesh: ArrayMesh = _joined_meshes[key]
 if mesh == null: return
 var draw := MeshInstance3D.new()
 draw.name = "EstateSurfaceBatch"
 draw.mesh = mesh
 draw.custom_aabb = bounds
 draw.material_override = first.material
 draw.layers = first.layers
 for i in range(FLAGS.size()): draw.set(FLAGS[i],first.flags[i])
 draw.set_meta("estate_instance_batch",true)
 var paths := PackedStringArray()
 for item: Dictionary in sources: paths.append(item.path)
 draw.set_meta("source_geometry_path",paths[0])
 draw.set_meta("source_geometry_paths",paths)
 _estate.add_child(draw)
 draw.global_transform = first.transform
 _register_group(sources,draw,world_bounds)

static func _append_indices(target: PackedInt32Array, bytes: PackedByteArray, count: int, offset: int) -> PackedInt32Array:
 var stride := 2 if count<=65536 else 4
 for i in range(bytes.size()/stride):
  target.append((bytes.decode_u16(i*stride) if stride==2 else bytes.decode_u32(i*stride))+offset)
 return target

static func _pack_indices(indices: PackedInt32Array, count: int) -> PackedByteArray:
 var stride := 2 if count<=65536 else 4
 var result := PackedByteArray(); result.resize(indices.size()*stride)
 for i in range(indices.size()):
  if stride==2:result.encode_u16(i*2,indices[i])
  else:result.encode_u32(i*4,indices[i])
 return result

static func join(sources: Array) -> ArrayMesh:
 if sources.is_empty(): return null
 var first: Dictionary = sources[0].mesh.get("_surfaces")[0]
 if first.format & Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES: return null
 var output := first.duplicate()
 var positions := PackedByteArray();var normals := PackedByteArray();var attributes := PackedByteArray()
 var indices := PackedInt32Array()
 var vertices := 0
 var bounds: AABB = first.aabb
 var surfaces: Array[Dictionary] = []
 var thresholds: Array[float] = []
 for item: Dictionary in sources:
  var surface: Dictionary = item.mesh.get("_surfaces")[0]
  if surface.format!=first.format or surface.get("uv_scale",Vector4.ZERO)!=first.get("uv_scale",Vector4.ZERO):return null
  if surface.primitive!=Mesh.PRIMITIVE_TRIANGLES or surface.get("skin_data",PackedByteArray()).size()>0:return null
  var count:int=surface.vertex_count
  var stride:=RenderingServer.mesh_surface_get_format_vertex_stride(surface.format,count)
  positions.append_array(surface.vertex_data.slice(0,count*stride))
  if surface.format & Mesh.ARRAY_FORMAT_NORMAL:
   var offset:=RenderingServer.mesh_surface_get_format_offset(surface.format,count,Mesh.ARRAY_NORMAL)
   normals.append_array(surface.vertex_data.slice(offset))
  attributes.append_array(surface.get("attribute_data",PackedByteArray()))
  indices=_append_indices(indices,surface.index_data,count,vertices)
  surface["vertex_offset"]=vertices
  surfaces.append(surface)
  var lods:Array=surface.get("lods",[])
  for i in range(0,lods.size(),2):
   var edge:float=lods[i]
   if edge>0.0 and edge not in thresholds:thresholds.append(edge)
  vertices+=count
  bounds=bounds.merge(surface.aabb)
 thresholds.sort()
 var selected:Array[float]=[]
 if thresholds.size()<=8:selected.assign(thresholds)
 else:
  for i in range(8): selected.append(thresholds[roundi(float(i)*(thresholds.size()-1)/7.0)])
 var joined_lods:Array=[]
 for edge:float in selected:
  var lod_indices:=PackedInt32Array()
  for surface:Dictionary in surfaces:
   var data:PackedByteArray=surface.index_data
   var lods:Array=surface.get("lods",[])
   for i in range(0,lods.size(),2):
    if float(lods[i])<=edge:data=lods[i+1]
   lod_indices=_append_indices(lod_indices,data,surface.vertex_count,surface.vertex_offset)
  joined_lods.append(edge)
  joined_lods.append(_pack_indices(lod_indices,vertices))
 positions.append_array(normals)
 output.vertex_data=positions;output.attribute_data=attributes
 output.vertex_count=vertices;output.index_count=indices.size();output.index_data=_pack_indices(indices,vertices)
 output.aabb=bounds;output.erase("material")
 if joined_lods.is_empty():output.erase("lods")
 else:output.lods=joined_lods
 var result:=ArrayMesh.new();result.set("_surfaces",[output]);result.custom_aabb=bounds
 return result
