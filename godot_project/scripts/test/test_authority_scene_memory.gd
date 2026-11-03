extends SceneTree

func _initialize() -> void: call_deferred("run")
func fail(message: String) -> void:
 push_error(message)
 quit(1)
func run() -> void:
 create_timer(45.0).timeout.connect(func(): fail("Authority verification timed out"))
 var before := OS.get_static_memory_usage()
 # Include main's dependencies: an unused lab preload must not retain the GLB.
 var main_script := load("res://main.gd") as Script
 if main_script == null:
  fail("Runtime entry must load");return
 var nest := load("res://rooms/nest.tscn").instantiate() as ModularNest
 nest.set("physical_authority", true)
 root.add_child(nest)
 for i in range(5): await process_frame
 var bytes := OS.get_static_memory_usage()-before
 print("AUTHORITY_MEMORY bytes=",bytes)
 if ResourceLoader.has_cached("res://rooms/estate/ElfieNest-complete-final.glb") or not nest.get_node("Generated").find_children("*", "MeshInstance3D", true, false).is_empty():
  fail("Hidden authority must not load or retain the display model");return
 if bytes > 900*1024*1024:
  fail("Authority exceeds the physical-only memory budget");return
 if nest.semantic_anchor_ids().size()!=92 or nest._estate_physics.collider_count!=1258 or nest._estate_physics._doors.size()!=10:
  fail("Authority must retain all anchors, colliders and sliding doors");return
 for anchor:String in ["central-01/sofa-left","central-01/sofa","central-01/sofa-right"]:
  var marker := nest.resolve_anchor(anchor)
  if marker == null or str(marker.get_meta("kind", "")) != "chair":
   fail("Authority must preserve each independent sofa seat: "+anchor);return
 if not nest.bake_navigation() or not await nest.wait_for_navigation_sync() or not nest.validate_navigation_anchors():
  fail("Authority physical navigation must remain connected");return
 var manifest := nest.scene_manifest()
 if manifest["zones"].size()!=21:
  fail("Authority must preserve the complete world's semantic zones");return
 var inspection := "terrace-04/lilac-game-armchair-3"
 if nest.resolve_anchor(inspection) != null or manifest["anchors"].size() != 92:
  fail("Inspection contacts must not become normal navigation targets");return
 nest.set_meta("lab_action_preview",true)
 if nest.resolve_anchor(inspection) == null or nest.scene_manifest()["anchors"].size() != 137 or not nest.validate_navigation_anchors():
  fail("Lab must expose all real furniture contacts from the same compiled scene");return
 var doors: Array=nest._estate_physics._doors
 for door: Dictionary in doors:
  if not is_instance_valid(door.body) or not is_instance_valid(door.mesh):
   fail("Every cached door must retain its transform and collision body");return
 var control=nest._estate_physics._door_controls[0]
 var original: Transform3D=doors[0]["closed"]
 var actors: Array[Node3D] = []
 control.advance(1.0,true,actors)
 if (doors[0]["body"] as Node3D).global_position.is_equal_approx(original.origin):
  fail("Cached sliding doors must still move their real collision body");return
 print("PASS physical-only authority: complete anchors, collisions, doors and navigation without display resources")
 nest.free()
 quit()
