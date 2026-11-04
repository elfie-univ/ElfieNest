extends RefCounted
## Remove only authored soil-bank geometry projecting above the real lake footprint.
static func is_bank(mesh: MeshInstance3D) -> bool:
 return str(mesh.name) in ["CY R003 corrected CY R002 lakeside returned solid planting bank","CY R003 corrected CY SHORE solid Continuous planted lake bank","CY R003 corrected CY SHORE solid Lake sloping bank","CY R003 corrected CY R002 continuous natural shore slope 0","CY R003 corrected CY R002 continuous natural shore slope 1"]

static func apply(estate: Node3D, water: PackedVector2Array, bounds: Rect2, height: float) -> int:
 # Clear the full shoreline ribbon rather than trimming only the water itself.
 var margin:=0.12
 var expanded:=Geometry2D.offset_polygon(water,margin,Geometry2D.JOIN_ROUND)
 assert(expanded.size()==1,"Bank trimming requires the single real lake footprint")
 var clip_water: PackedVector2Array=expanded[0]
 var total:=0
 for node: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
  if not is_bank(node):continue
  var source:=node.mesh
  var result:=ArrayMesh.new()
  var removed:=0
  for surface in range(source.get_surface_count()):
   var arrays:=source.surface_get_arrays(surface).duplicate(true)
   var vertices: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
   var ids: PackedInt32Array=arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX]!=null else PackedInt32Array()
   var count:=ids.size() if not ids.is_empty() else vertices.size()
   var kept:=PackedInt32Array()
   for i in range(0,count,3):
    var tri:=PackedInt32Array()
    var world:=PackedVector3Array()
    for j in range(3):
     var index:=ids[i+j] if not ids.is_empty() else i+j
     tri.append(index);world.append(node.global_transform*vertices[index])
    var top:=maxf(world[0].y,maxf(world[1].y,world[2].y))
    var polygon:=PackedVector2Array()
    for point in world:polygon.append(Vector2(point.x,point.z))
    var box:=Rect2(polygon[0],Vector2.ZERO).expand(polygon[1]).expand(polygon[2])
    if top<=height+0.015 or not bounds.grow(margin).intersects(box,true):
     kept.append_array(tri);continue
    var area: float=(polygon[1]-polygon[0]).cross(polygon[2]-polygon[0])
    if absf(area)<0.0000001:
     var center: Vector2=(polygon[0]+polygon[1]+polygon[2])/3.0
     if bounds.has_point(center) and (Geometry2D.is_point_in_polygon(center,water) or Geometry2D.is_point_in_polygon(center,clip_water)):removed+=1
     else:kept.append_array(tri)
     continue
    if Geometry2D.intersect_polygons(polygon,clip_water).is_empty():
     kept.append_array(tri);continue
    removed+=1
    for outside: PackedVector2Array in Geometry2D.clip_polygons(polygon,clip_water):
     var cut:=Geometry2D.triangulate_polygon(outside)
     var offset: int=arrays[Mesh.ARRAY_VERTEX].size()
     for point: Vector2 in outside:
      var wb: float=(point-polygon[0]).cross(polygon[2]-polygon[0])/area
      var wc: float=(polygon[1]-polygon[0]).cross(point-polygon[0])/area
      var weights:=Vector3(1.0-wb-wc,wb,wc)
      _append_vertex(arrays,tri,weights)
     for j in range(0,cut.size(),3):
      var a:=offset+cut[j];var b:=offset+cut[j+1];var c:=offset+cut[j+2]
      var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
      var normal: Vector3=(world[1]-world[0]).cross(world[2]-world[0])
      var generated: Vector3=node.global_basis*((points[b]-points[a]).cross(points[c]-points[a]))
      kept.append_array(PackedInt32Array([a,b,c] if generated.dot(normal)>=0.0 else [a,c,b]))
   # Degenerate projection slivers can survive a polygon difference. Enforce
   # the water-plane invariant against the original footprint as well.
   var final_ids:=PackedInt32Array()
   var points: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
   for j in range(0,kept.size(),3):
    var center: Vector3=node.global_transform*((points[kept[j]]+points[kept[j+1]]+points[kept[j+2]])/3.0)
    var xz:=Vector2(center.x,center.z)
    if center.y>height+0.015 and bounds.has_point(xz) and Geometry2D.is_point_in_polygon(xz,water):removed+=1;continue
    final_ids.append_array(kept.slice(j,j+3))
   if final_ids.is_empty():continue
   arrays[Mesh.ARRAY_INDEX]=final_ids
   result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
   result.surface_set_material(result.get_surface_count()-1,node.get_active_material(surface))
  if removed>0:
   total+=removed
   node.set_meta("lake_bank_clipped_triangles",removed)
   if result.get_surface_count()>0:
    node.mesh=result
    for s in range(result.get_surface_count()):node.set_surface_override_material(s,null)
   else:node.hide()
 return total

static func _append_vertex(arrays: Array, tri: PackedInt32Array, weights: Vector3) -> void:
 for channel in [Mesh.ARRAY_VERTEX,Mesh.ARRAY_NORMAL,Mesh.ARRAY_TEX_UV,Mesh.ARRAY_TEX_UV2,Mesh.ARRAY_COLOR]:
  if arrays[channel]==null or arrays[channel].is_empty():continue
  var values=arrays[channel]
  var value=values[tri[0]]*weights.x+values[tri[1]]*weights.y+values[tri[2]]*weights.z
  if channel==Mesh.ARRAY_NORMAL:value=value.normalized()
  values.append(value);arrays[channel]=values
 if arrays[Mesh.ARRAY_TANGENT]!=null and not arrays[Mesh.ARRAY_TANGENT].is_empty():
  var tangents: PackedFloat32Array=arrays[Mesh.ARRAY_TANGENT]
  for k in range(4):tangents.append(tangents[tri[0]*4+k]*weights.x+tangents[tri[1]*4+k]*weights.y+tangents[tri[2]*4+k]*weights.z)
  arrays[Mesh.ARRAY_TANGENT]=tangents
