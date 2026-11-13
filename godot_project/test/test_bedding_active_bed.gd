extends SceneTree
var BEDDING: Script = preload("res://nest/furniture/shared/bedroom/estate_bedding_layers.gd")
func _initialize() -> void: call_deferred("run")
func run() -> void:
 var estate := Node3D.new();root.add_child(estate)
 var first := fixture();estate.add_child(first)
 var second := fixture();estate.add_child(second)
 for mesh: MeshInstance3D in second.get_children(): mesh.set_meta("extras",{"piece":str(mesh.name),"module":"M02","resident":"A"})
 var cloth := first.get_node("bed_cover") as MeshInstance3D
 var throw_mesh := first.get_node("throw") as MeshInstance3D
 var original := throw_mesh.mesh
 if not BEDDING.has_method("attach_bed"):
  push_error("Split runtime has no lazy binding for an active bed");quit(1);return
 BEDDING.attach_bed(estate,cloth)
 var binding: RefCounted = cloth.get_meta("estate_bedding_layers")
 if throw_mesh.mesh != original or second.get_node("bed_cover").has_meta("estate_bedding_layers"):
  push_error("Active bed binding changed authored rest or touched another room");quit(1);return
 var moved := mesh_at(0.3)
 cloth.mesh = moved
 binding.sample(moved.surface_get_arrays(0)[Mesh.ARRAY_VERTEX])
 var actual: PackedVector3Array = throw_mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
 var source: PackedVector3Array = original.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
 for i in range(actual.size()):
  if not actual[i].is_equal_approx(source[i]+Vector3.UP*0.3):
   push_error("Authored bedding offset was changed");quit(1);return
 var dynamic := throw_mesh.mesh
 binding.sample(moved.surface_get_arrays(0)[Mesh.ARRAY_VERTEX])
 if throw_mesh.mesh != dynamic:
  push_error("Unchanged bedding unnecessarily replaced its mesh");quit(1);return
 binding.restore()
 if throw_mesh.mesh != original:
  push_error("Active bed did not restore its exact authored resource");quit(1);return
 BEDDING.attach_bed(estate,cloth)
 if binding.layers.size()!=1:
  push_error("Repeated bed use duplicated bindings");quit(1);return
 estate.free()
 print("PASS lazy active-bed binding, room isolation, exact offsets and restoration")
 quit()

func mesh_at(height: float) -> ArrayMesh:
 var arrays:=[];arrays.resize(Mesh.ARRAY_MAX)
 arrays[Mesh.ARRAY_VERTEX]=PackedVector3Array([Vector3(0,height,0),Vector3(1,height,0),Vector3(1,height,1),Vector3(0,height,1)])
 arrays[Mesh.ARRAY_NORMAL]=PackedVector3Array([Vector3.UP,Vector3.UP,Vector3.UP,Vector3.UP])
 arrays[Mesh.ARRAY_INDEX]=PackedInt32Array([0,2,1,0,3,2])
 var mesh:=ArrayMesh.new();mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays);return mesh
func fixture() -> Node3D:
 var rig:=Node3D.new()
 for piece in ["bed_cover","throw"]:
  var node:=MeshInstance3D.new();node.name=piece
  node.mesh=mesh_at(0.0 if piece=="bed_cover" else 0.02)
  node.set_meta("extras",{"piece":piece,"module":"M01","resident":"A"})
  rig.add_child(node)
 return rig
