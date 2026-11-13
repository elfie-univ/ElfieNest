extends SceneTree
const BANKS=preload("res://nest/courtyard/parts/waterside/estate_bank_cleanup.gd")
func _initialize():call_deferred("run")
func run():
 create_timer(90.0).timeout.connect(func():quit(1))
 var estate=load("res://nest/assembly/estate.tscn").instantiate()
 root.add_child(estate)
 var shore=preload("res://test/split_estate_test_support.gd").shore_geometry(estate)
 var failures=[]
 for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
  if not BANKS.is_bank(mesh) or not mesh.is_visible_in_tree():continue
  var faces=mesh.mesh.get_faces()
  for i in range(0,faces.size(),3):
   var point=mesh.global_transform*((faces[i]+faces[i+1]+faces[i+2])/3.0)
   if point.y>shore.water_height+0.015 and shore.water_bounds.has_point(Vector2(point.x,point.z)) and Geometry2D.is_point_in_polygon(Vector2(point.x,point.z),shore.water):
    failures.append("Exposed bank triangle over water: "+str(mesh.name)+" at "+str(point));break
 if not failures.is_empty():
  for message in failures:push_error(message)
  estate.free();quit(1);return
 var probe=BoxMesh.new();probe.size=Vector3(0.1,0.1,0.1);probe.material=StandardMaterial3D.new()
 var buffer=PackedFloat32Array()
 var positions=[shore.bench_clearance.get_center(),Vector3(33,shore.water_height+0.05,20),Vector3(-40,2,-20)]
 for point: Vector3 in positions:buffer.append_array(PackedFloat32Array([1,0,0,point.x,0,1,0,point.y,0,0,1,point.z]))
 var filtered=shore.filter_plant_instances(probe,buffer)
 if filtered.indices!=PackedInt32Array([2]):failures.append("Instance pruning must remove bench/water intrusions, preserving unrelated source IDs")
 # Validate every saved placement; source IDs and old BIN pruning counters are
 # replaced by the canonical SCN batches. Measure the actual retained geometry.
 var canonical_error=preload("res://test/split_estate_test_support.gd").batch_error(estate)
 if not canonical_error.is_empty():failures.append(canonical_error)
 for batch: MultiMeshInstance3D in estate.find_children("*","MultiMeshInstance3D",true,false):
  var data=preload("res://test/split_estate_test_support.gd").canonical_batch(batch)
  if data.is_empty():continue
  var world_buffer=PackedFloat32Array()
  for index in range(data.instance_count):
   var pose=batch.global_transform*preload("res://test/split_estate_test_support.gd").instance_transform(batch,index)
   world_buffer.append_array(PackedFloat32Array([pose.basis.x.x,pose.basis.y.x,pose.basis.z.x,pose.origin.x,pose.basis.x.y,pose.basis.y.y,pose.basis.z.y,pose.origin.y,pose.basis.x.z,pose.basis.y.z,pose.basis.z.z,pose.origin.z]))
  var clearance=shore.filter_plant_instances(batch.multimesh.mesh,world_buffer)
  if not clearance.removed.is_empty():failures.append("Canonical landscape intrudes into bench/water clearance: "+str(batch.get_path()))
 for message in failures:push_error(message)
 print("LAKESIDE_CLEARANCE banks=",estate.get_meta("bank_triangles_clipped",0)," bench_instances=",estate.get_meta("foliage_pruned_bench",0)," water_instances=",estate.get_meta("foliage_pruned_water",0)," failures=",failures.size())
 estate.free();quit(0 if failures.is_empty() else 1)
