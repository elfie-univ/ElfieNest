extends SceneTree
const PATH := "res://nest/rendering/estate_surface_batches.gd"
var failures := 0
func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
 if not ok: failures += 1; push_error(message)
func mesh_at(x: float, edge: float) -> ArrayMesh:
 var arrays := []; arrays.resize(Mesh.ARRAY_MAX)
 arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(x,0,0),Vector3(x+0.2,0,0),Vector3(x,0,0.2),Vector3(x+0.2,0,0.2)])
 arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP,Vector3.UP,Vector3.UP,Vector3.UP])
 arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.RIGHT,Vector2.UP,Vector2.ONE])
 arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,2,1,1,2,3])
 var mesh := ArrayMesh.new()
 mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays,[],{edge:PackedInt32Array([0,2,1])})
 mesh.set_meta("nest_source_library","res://nest/furniture/shared/bedroom/bedroom-planters.glb")
 return mesh
func indices(surface: Dictionary, threshold: float) -> PackedInt32Array:
 var data: PackedByteArray = surface.index_data
 var lods: Array = surface.get("lods",[])
 for i in range(0,lods.size(),2):
  if float(lods[i])<=threshold: data=lods[i+1]
 var result := PackedInt32Array()
 var stride := 2 if int(surface.vertex_count)<=65536 else 4
 for i in range(data.size()/stride):result.append(data.decode_u16(i*stride) if stride==2 else data.decode_u32(i*stride))
 return result
func run() -> void:
 if not ResourceLoader.exists(PATH):check(false,"Missing exact surface batcher");quit(1);return
 var script:Script=load(PATH)
 var first:=mesh_at(0.0,0.1);var second:=mesh_at(0.3,0.4)
 var source:=[{"mesh":first},{"mesh":second}]
 var merged:ArrayMesh=script.join(source)
 check(merged!=null,"Compatible original surfaces must merge")
 if merged==null:quit(1);return
 var actual:=merged.surface_get_arrays(0)
 for slot:int in [Mesh.ARRAY_VERTEX,Mesh.ARRAY_NORMAL,Mesh.ARRAY_TEX_UV]:
  var expected:Variant=first.surface_get_arrays(0)[slot].duplicate()
  expected.append_array(second.surface_get_arrays(0)[slot])
  check(var_to_bytes(expected)==var_to_bytes(actual[slot]),"Decoded original attributes changed: "+str(slot))
 var surface:Dictionary=merged.get("_surfaces")[0]
 check(not surface.get("lods",[]).is_empty(),"Keep authored reduced LODs")
 for threshold:float in [0.0,0.05,0.1,0.2,0.4,1.0]:
  var expected:=indices(first.get("_surfaces")[0],threshold)
  for index:int in indices(second.get("_surfaces")[0],threshold):expected.append(index+4)
  check(indices(surface,threshold)==expected,"Merged LOD must use exactly the matching original triangle indices")
 var world:=Node3D.new();root.add_child(world)
 var material:=ShaderMaterial.new();material.shader=load("res://nest/furniture/shared/bedroom/m01_sheen.gdshader")
 var nodes:Array[MeshInstance3D]=[]
 for mesh:Mesh in [first,second]:
  var node:=MeshInstance3D.new();node.mesh=mesh;node.material_override=material;world.add_child(node);nodes.append(node)
 var batcher:Node=script.new();world.add_child(batcher);batcher.bind(world)
 check(batcher.groups.size()==1,"Same-frame pieces with distinct meshes should share one draw")
 if not batcher.groups.is_empty():
  var draw:MeshInstance3D=batcher.groups[0].draw
  check(draw.material_override==material,"Keep original fabric shader material")
  check(nodes[0].mesh==first and nodes[1].mesh==second,"Retain original subpart meshes for inspection")
  nodes[1].mesh=mesh_at(0.3,0.4)
  batcher.poll()
  check(not draw.visible and nodes[0].layers==1 and nodes[1].layers==1,"Cloth mesh replacement restores the original nodes before drawing")
 world.free()
 print("ESTATE_SURFACE_BATCHES failures=",failures)
 quit(1 if failures else 0)
