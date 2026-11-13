extends RefCounted
## Named verification routes derived exclusively from the loaded world geometry.

static func points(nest: ModularNest, id: String, bed: String) -> PackedVector3Array:
 var result := PackedVector3Array()
 var anchors: Array[String] = []
 if id.begins_with("door-"):
  return navigable(nest,nest._estate_physics.preview_door_path(id))
 match id:
  "morning": anchors.assign([bed, "central-02/activity", "terrace-01/activity", "central-02/activity"])
  "evening": anchors.assign(["central-01/activity", "courtyard/activity", bed])
  "arrival": anchors.assign(["central-04/activity", "central-03/activity", "central-02/activity", "central-01/activity"])
  "seats": anchors.assign(["central-01/sofa-left", "central-01/sofa", "central-01/sofa-right"])
  "forest", "ring", "lake":
   var estate := nest.get_node_or_null("Generated/CompleteEstate")
   if estate == null: return result
   for mesh: MeshInstance3D in estate.find_children("*", "MeshInstance3D", true, false):
    var name := str(mesh.get_meta("extras", {}).get("source_name", mesh.name))
    if id == "forest" and name == "FOREST TRAIL smooth gravel main loop and return spur":
     result = forest_path(mesh)
     break
    if (id == "ring" and name == "ROAD REF • ring continuous warm-grey stone bed") or (id == "lake" and name == "CY R003 circular waterfront platform closed foundation"):
     var bounds := mesh.global_transform * mesh.get_aabb()
     var center := bounds.get_center()
     if id == "lake":
      # The platform includes a westward connecting tongue; its circular
      # eastern end has the diameter of the authored north/south bounds.
      center.x = bounds.end.x - bounds.size.z * 0.5
     for index in range(12):
      var angle := TAU * float(index) / 12.0
      var margin := -0.7 if id == "lake" else -0.5
      var radius_x := bounds.size.z * 0.5 if id == "lake" else bounds.size.x * 0.5
      result.append(Vector3(center.x + cos(angle)*(radius_x+margin), bounds.end.y+0.02, center.z+sin(angle)*(bounds.size.z*0.5+margin)))
     break
   if not result.is_empty(): result.append(result[0])
 for anchor: String in anchors:
  var marker := nest.resolve_anchor(anchor)
  if marker == null: return PackedVector3Array()
  result.append(marker.global_position)
 return navigable(nest, result)

static func forest_path(mesh: MeshInstance3D) -> PackedVector3Array:
 # The formal trail is an open paved band with two entrances and a return
 # spur. Follow its actual connected triangles, not retired authoring extras
 # or a straight chord across the woodland. Navigation then supplies clearance.
 if mesh.has_meta("demonstration_forest_path"):
  return mesh.get_meta("demonstration_forest_path")
 var graph := AStar3D.new()
 var ids := {}
 var middle := mesh.get_aabb().get_center().x
 var entrances := [-1, -1]
 var south := [-INF, -INF]
 var faces := mesh.mesh.get_faces()
 for face in range(0, faces.size(), 3):
  var vertices := PackedInt64Array()
  for offset in range(3):
   var p: Vector3 = faces[face + offset]
   var key := p.snapped(Vector3.ONE * 0.001)
   if not ids.has(key):
    var id := ids.size()
    ids[key] = id
    graph.add_point(id, mesh.to_global(p))
    var side := 0 if p.x < middle else 1
    if p.z > south[side]:
     south[side] = p.z
     entrances[side] = id
   vertices.append(ids[key])
  for edge in range(3):
   var a := vertices[edge]
   var b := vertices[(edge + 1) % 3]
   if a != b and not graph.are_points_connected(a, b): graph.connect_points(a, b)
 var result := PackedVector3Array()
 if entrances[0] >= 0 and entrances[1] >= 0:
  var path := graph.get_point_path(entrances[0], entrances[1])
  for index in range(path.size()):
   if result.is_empty() or result[-1].distance_to(path[index]) >= 1.0 or index == path.size()-1:
    result.append(path[index])
 mesh.set_meta("demonstration_forest_path", result)
 return result

static func navigable(nest: ModularNest, points_to_check: PackedVector3Array) -> PackedVector3Array:
 var map := nest.get_world_3d().navigation_map
 if NavigationServer3D.map_get_iteration_id(map) == 0: return PackedVector3Array()
 var result := PackedVector3Array()
 for point: Vector3 in points_to_check:
  var target := NavigationServer3D.map_get_closest_point(map, point)
  if target.distance_to(point) > 2.0: return PackedVector3Array()
  if not result.is_empty():
   var path := NavigationServer3D.map_get_path(map,result[-1],target,true)
   if path.is_empty() or path[-1].distance_to(target)>0.3: return PackedVector3Array()
  result.append(target)
 return result
