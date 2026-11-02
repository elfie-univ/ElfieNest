extends SceneTree
const BANKS=preload("res://rooms/estate/estate_bank_cleanup.gd")
func _initialize():call_deferred("run")
func run():
 create_timer(90.0).timeout.connect(func():quit(1))
 var estate=load("res://rooms/estate/estate.tscn").instantiate()
 root.add_child(estate)
 var shore=estate.get("_shore")
 var failures=[]
 for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
  if not BANKS.is_bank(mesh) or not mesh.is_visible_in_tree():continue
  var faces=mesh.mesh.get_faces()
  for i in range(0,faces.size(),3):
   var point=mesh.global_transform*((faces[i]+faces[i+1]+faces[i+2])/3.0)
   if point.y>shore.water_height+0.015 and shore.water_bounds.has_point(Vector2(point.x,point.z)) and Geometry2D.is_point_in_polygon(Vector2(point.x,point.z),shore.water):
    failures.append("Exposed bank triangle over water: "+str(mesh.name)+" at "+str(point));break
 if int(estate.get_meta("foliage_pruned_bench",0))==0:failures.append("No actual leaves/secondary branches were removed from the seating clearance")
 if int(estate.get_meta("bank_triangles_clipped",0))==0:failures.append("The actual lake bank fragments were not corrected")
 print("LANDSCAPE_COUNTS banks=",estate.get_meta("bank_triangles_clipped",0)," bench=",estate.get_meta("foliage_pruned_bench",0)," water=",estate.get_meta("foliage_pruned_water",0))
 if not failures.is_empty():
  for message in failures:push_error(message)
  estate.free();quit(1);return
 var probe=BoxMesh.new();probe.size=Vector3(0.1,0.1,0.1);probe.material=StandardMaterial3D.new()
 var buffer=PackedFloat32Array()
 var positions=[shore.bench_clearance.get_center(),Vector3(33,shore.water_height+0.05,20),Vector3(-40,2,-20)]
 for point: Vector3 in positions:buffer.append_array(PackedFloat32Array([1,0,0,point.x,0,1,0,point.y,0,0,1,point.z]))
 var filtered=shore.filter_plant_instances(probe,buffer)
 if filtered.indices!=PackedInt32Array([2]):failures.append("Instance pruning must remove bench/water intrusions, preserving unrelated source IDs")
 var retained: Dictionary={}
 for node: Node in estate.get_children():
  if not node is MultiMeshInstance3D:continue
  var group: String=str(node.get_meta("source_group"))
  if not retained.has(group):retained[group]={}
  for index: int in node.get_meta("source_instance_indices"):
   if retained[group].has(index):failures.append("Duplicate retained source ID: "+group)
   retained[group][index]=true
 var sidecar=FileAccess.open("res://rooms/estate/ElfieNest-complete-final.instances.bin",FileAccess.READ)
 sidecar.seek(12)
 var groups=sidecar.get_32();sidecar.get_32()
 var pruned: Dictionary=estate.get_meta("foliage_pruned_by_group",{})
 for gi in range(groups):
  var name_size=sidecar.get_32();var count=sidecar.get_32();var group=sidecar.get_buffer(name_size).get_string_from_utf8()
  var kept: Dictionary=retained.get(group,{})
  var removed: PackedInt32Array=pruned.get(group,PackedInt32Array())
  for index in removed:
   if index<0 or index>=count or kept.has(index):failures.append("Removed source ID is invalid or still rendered: "+group)
  if kept.size()+removed.size()!=count:failures.append("Unclassified source instances: "+group)
  sidecar.seek(sidecar.get_position()+count*CompleteEstateFinal.INSTANCE_BYTES)
 sidecar.close()
 var actual=int(estate.get("multimesh_instance_count"))+int(estate.get_meta("foliage_pruned_count",0))
 if actual!=214448:failures.append("Pruning must account for every original instance")
 for message in failures:push_error(message)
 print("LAKESIDE_CLEARANCE banks=",estate.get_meta("bank_triangles_clipped",0)," bench_instances=",estate.get_meta("foliage_pruned_bench",0)," water_instances=",estate.get_meta("foliage_pruned_water",0)," failures=",failures.size())
 estate.free();quit(0 if failures.is_empty() else 1)
