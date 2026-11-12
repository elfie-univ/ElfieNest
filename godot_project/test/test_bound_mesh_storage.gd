extends SceneTree
## Bound placements store source references, never redundant renderer buffers.
const BINDING := preload("res://nest/assembly/glb_placement.gd")
func _initialize() -> void:call_deferred("run")
static func stored_mesh_count(scene: Node3D) -> int:
 var count := 0
 for binding: Node in scene.find_children("*","Node3D",true,false):
  if binding.get_script()!=BINDING:continue
  for child: Node in binding.get_children():
   if child is MeshInstance3D and child.mesh!=null:count+=1
   elif child is MultiMeshInstance3D and child.multimesh!=null:count+=1
 return count
func run() -> void:
 var scene: Node3D=(load("res://nest/buildings/building-layout.scn") as PackedScene).instantiate()
 if stored_mesh_count(scene)>0:
  scene.free();push_error("Building placements still serialize redundant GLB mesh buffers");quit(1);return
 root.add_child(scene)
 for binding: Node in scene.find_children("*","Node3D",true,false):
  if binding.get_script()!=BINDING:continue
  for child: Node in binding.get_children():
   if child is MeshInstance3D and child.mesh==null or child is MultiMeshInstance3D and (child.multimesh==null or child.multimesh.mesh==null):
    scene.free();push_error("Removing stored buffers lost a source mesh at load");quit(1);return
 scene.free();print("BUILDING_REFERENCES_ONLY_AND_ALL_MESHES_REBOUND_OK");quit(0)
