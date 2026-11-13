extends "res://../build/godot-asset-migration/evaluated-v044/capture.gd"
func run() -> void:
 var world := (load("res://../build/godot-asset-migration/evaluated-v044/v044-evaluated-static.scn") as PackedScene).instantiate()
 root.add_child(world)
 var cache := {}
 var records := {}
 for node: MeshInstance3D in world.find_children("*", "MeshInstance3D", true, false):
  var identity: int = node.mesh.get_instance_id()
  if not cache.has(identity):
   var surfaces: Array = []
   for surface in node.mesh.get_surface_count():
    var arrays := node.mesh.surface_get_arrays(surface)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var context := HashingContext.new()
    context.start(HashingContext.HASH_SHA256)
    context.update(vertices.to_byte_array())
    surfaces.append({"vertices": vertices.size(), "position_sha256": context.finish().hex_encode()})
   cache[identity] = surfaces
  records[str(world.get_path_to(node))] = cache[identity]
 var file := FileAccess.open("res://../build/godot-asset-migration/source-vertex-fingerprints.json",FileAccess.WRITE)
 file.store_string(JSON.stringify(records));file.close()
 print("SOURCE_VERTEX_FINGERPRINTS ",records.size()," unique_meshes=",cache.size())
 world.free();quit(0)
