extends SceneTree
## Construction lookup storage must not survive finished bedding bindings.
const BEDDING := preload("res://nest/estate/estate_bedding_layers.gd")
func _initialize() -> void: call_deferred("run")
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
func run() -> void:
 var rig:=fixture();root.add_child(rig);BEDDING.attach(rig)
 var cloth:=rig.get_node("bed_cover") as MeshInstance3D
 var binding: RefCounted=cloth.get_meta("estate_bedding_layers")
 if not binding._cells.is_empty() or not binding._points.is_empty():
  push_error("Completed bedding binding retained construction lookup buffers");quit(1);return
 # Reconstruct the old retained lookup state in an independent reference rig.
 var reference:=fixture();root.add_child(reference);BEDDING.attach(reference)
 var reference_cloth:=reference.get_node("bed_cover") as MeshInstance3D
 var retained: RefCounted=reference_cloth.get_meta("estate_bedding_layers")
 retained._bind(reference_cloth)
 for height in [0.0,0.3,0.6,0.0]:
  cloth.mesh=binding.rest if height==0.0 else mesh_at(height)
  reference_cloth.mesh=retained.rest if height==0.0 else mesh_at(height)
  binding.sample();retained.sample()
  var actual: Mesh=(rig.get_node("throw") as MeshInstance3D).mesh
  var expected: Mesh=(reference.get_node("throw") as MeshInstance3D).mesh
  if var_to_bytes(actual.surface_get_arrays(0))!=var_to_bytes(expected.surface_get_arrays(0)):
   push_error("Lookup release changed bedding corner attributes");quit(1);return
 var original: Mesh=(rig.get_node("throw") as MeshInstance3D).mesh
 BEDDING.attach(rig)
 if (rig.get_node("throw") as MeshInstance3D).mesh!=original:
  push_error("Repeated attachment rebuilt bound bedding");quit(1);return
 print("BEDDING_STORAGE lookup_empty=true rest_and_deformation_exact=true repeated_attach=true")
 rig.free();reference.free();quit()
