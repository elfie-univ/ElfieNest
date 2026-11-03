extends SceneTree
const NEST := preload("res://rooms/nest.tscn")
const CONTROLLER := preload("res://runtime/actor/actor_controller.gd")
const DEMOS := preload("res://runtime/actor/action_demonstrations.gd")
const CONSOLE := preload("res://runtime/lab/nest_lab_console.gd")
var failed := false
func _initialize() -> void: call_deferred("run")
func require(ok: bool, message: String) -> bool:
 if not ok:
  push_error(message)
  failed=true
  quit(1)
 return ok
func run() -> void:
 Engine.time_scale=4.0
 Engine.physics_ticks_per_second=240
 create_timer(1200).timeout.connect(func()->void: push_error("Demonstration timeout");quit(1))
 var nest := NEST.instantiate() as ModularNest
 root.add_child(nest)
 await process_frame
 var configured := nest.apply_world_config({"nest_id":"preview-test","bed_count":32,"world_revision":1})
 if not require(configured.get("accepted",false),"World did not configure"): return
 if not require(nest.bake_navigation(),"Navigation did not load"):return
 if not require(await nest.wait_for_navigation_sync(),"Navigation did not synchronize"):return
 if not require(nest.validate_navigation_anchors(),"World anchor validation failed"):return
 var characters := Node3D.new()
 root.add_child(characters)
 var controller := CONTROLLER.new()
 root.add_child(controller)
 controller.setup(nest,characters,{"tovren":load("res://characters/tovren/tovren.tscn")},true)
 var accepted := controller.sync_actors([{"actor_id":"preview-actor","species":"tovren","appearance":{},"spawn_anchor_id":"dorm-01/bed-01"}])
 if not require(accepted.get("accepted",false),"Actor rejected"):return
 var demos := DEMOS.new()
 root.add_child(demos)
 demos.setup(nest,controller)
 controller.preview_demonstrations=demos
 nest.set_meta("lab_action_preview",true)
 var console := CONSOLE.new()
 root.add_child(console)
 console.setup(nest,characters)
 console.camera_command({"action":"environment","environment":{"phase":"dusk","lights_on":true,"quiet_mode":false}})
 if not require(console.camera_command({"action":"scene","target":"door-0","mode":"open"}),"Cannot preview door"):return
 if not require(console.camera_command({"action":"scene","target":"fountain","paused":true}),"Cannot pause fountain"):return
 var water := nest.get_node("Generated/ObserverFountainLighting")
 if not require(water.component_paused("fountain") and not water.component_paused("lake"),"Independent water pause failed"):return
 water.set_component_paused("fountain",false)
 water.set_component_paused("lake",true)
 water.sample(20.0,false)
 var frozen := float((water.lake.get_active_material(0) as ShaderMaterial).get_shader_parameter("presentation_time"))
 water.sample(21.0,false)
 if not require(is_equal_approx(frozen,float((water.lake.get_active_material(0) as ShaderMaterial).get_shader_parameter("presentation_time"))),"Lake shader did not pause"):return
 water.set_component_paused("lake",false)
 var items := demos.catalog("preview-actor")
 for item:Dictionary in items: print("DEMO_CATALOG ",JSON.stringify(item))
 var selected := OS.get_environment("ELFIENEST_DEMO_TEST_CASE")
 for item:Dictionary in items:
  if not selected.is_empty() and item.id not in selected.split(","):continue
  if not require(item.available,"Route not navigable: "+str(item.id)):return
  print("DEMO_START ",item.id)
  await demos.play("preview-actor",item.id)
  print("DEMO_RESULT ",item.id," ",demos.states.get("preview-actor"))
  if not require(demos.states.get("preview-actor")=="演示完成","Demo failed: "+str(item.id)):return
 if "door-0" in selected.split(","):
  console.camera_command({"action":"scene","target":"door-0","mode":"auto"})
  await demos.play("preview-actor","door-0")
  print("DOOR_DEMO_RESULT ",demos.states.get("preview-actor"))
  if not require(demos.states.get("preview-actor")=="演示完成","Door passage failed"):return
  await create_timer(4.0).timeout
  if not require(float(nest._estate_physics._doors[0]["amount"])<0.02,"Door did not close after passage"):return
 if "occupancy" in selected.split(","):
  if not await test_occupancy(controller):return
 if "cancel" in selected.split(","):
  if not await test_replacement(controller,demos):return
 nest.queue_free()
 characters.queue_free()
 controller.queue_free()
 demos.queue_free()
 console.queue_free()
 await process_frame
 print("PASS demonstrations world")
 quit(0)

func test_occupancy(controller: Node) -> bool:
 var admitted:Dictionary=controller.sync_actors([
  {"actor_id":"preview-actor","species":"tovren","appearance":{},"spawn_anchor_id":"dorm-01/bed-01"},
  {"actor_id":"second-actor","species":"tovren","appearance":{},"spawn_anchor_id":"dorm-01/bed-02"}])
 if not require(admitted.get("accepted",false),"Second actor rejected"):return false
 var terminal:Dictionary={}
 controller.runtime_event.connect(func(name:String,payload:Dictionary,_cause:String)->void:
  if name=="intent_terminal":terminal[payload.command_id]=payload)
 for spec:Array in [["seat-a","preview-actor","central-01/sofa-left"],["conflict","second-actor","central-01/sofa-left"],["seat-b","second-actor","central-01/sofa-right"]]:
  controller.execute_intent({"command_id":spec[0],"intent_id":spec[0],"actor_id":spec[1],"initiator":"elfie","body_generation":1,"intent":"use_anchor","anchor_id":spec[2],"furniture_cycle":"seat","deadline_seconds":120.0})
 if not require(terminal.get("conflict",{}).get("reason")=="furniture_occupied","Occupied seat was not rejected"):return false
 while not terminal.has("seat-a") or not terminal.has("seat-b"):await physics_frame
 print("MULTI_SEAT ",JSON.stringify(terminal))
 return require(terminal["seat-a"].status=="completed" and terminal["seat-b"].status=="completed","Simultaneous seat cycles failed")

func test_replacement(controller: Node, demos: Node) -> bool:
 var terminal:Dictionary={}
 controller.runtime_event.connect(func(name:String,payload:Dictionary,_cause:String)->void:
  if name=="intent_terminal":terminal[payload.command_id]=payload)
 demos.play("preview-actor","morning")
 var body:ElfieActor=controller.actor("preview-actor")
 while body.furniture_cycle_command.is_empty():await physics_frame
 # A single action must interrupt a complete furniture demonstration, and a
 # cancelled replacement must not start later when the old cycle releases.
 controller.execute_intent({"command_id":"replace-cancelled","actor_id":"preview-actor","intent":"emotion_expression","expression":"idle"})
 controller.cancel_intent({"command_id":"replace-cancelled","actor_id":"preview-actor"})
 controller.execute_intent({"command_id":"replace-latest","actor_id":"preview-actor","intent":"emotion_expression","expression":"idle"})
 while not terminal.has("replace-latest"):await physics_frame
 print("REPLACEMENT_RESULT ",JSON.stringify(terminal))
 if not require(terminal.get("replace-cancelled",{}).get("status")=="cancelled","Queued replacement did not cancel"):return false
 if not require(terminal["replace-latest"].status=="completed","Latest replacement did not execute"):return false
 return require(not demos.running("preview-actor") and body.furniture_cycle_command.is_empty(),"Old demonstration is still running")
