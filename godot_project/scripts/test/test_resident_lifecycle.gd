extends SceneTree
## Production admission trajectory, hosted body identity, cover and world door policy.
const CONTROLLER := preload("res://runtime/actor/actor_controller.gd")
const ARRIVAL := preload("res://runtime/actor/adoption_arrival.gd")
const PRESENTATION := preload("res://runtime/observer/resident_effects.gd")
const SAEVI := preload("res://characters/saevi/saevi.tscn")
var _failed := false

func _initialize() -> void:
 call_deferred("run")

func check(value: bool, message: String) -> bool:
 if value: return true
 push_error(message)
 _failed = true
 quit(1)
 return false

func run() -> void:
 var main_scene := load("res://main.tscn") as PackedScene
 if not check(main_scene != null, "Main scene failed after review retirement"): return
 var main := main_scene.instantiate()
 if not check(main.get_script() != null, "Main startup script did not parse"): return
 main.free()
 var lab := load("res://runtime/lab/lab_runtime.gd") as GDScript
 if not check(lab != null and lab.can_instantiate(), "Retained Nest Lab bridge did not parse"): return
 var nest := ModularNest.new()
 var camera := Camera3D.new()
 camera.name = "Camera3D"
 nest.add_child(camera)
 var hud: Node = load("res://ui/observation_hud.tscn").instantiate()
 hud.name = "ObservationHUD"
 nest.add_child(hud)
 root.add_child(nest)
 await process_frame
 var config := nest.apply_world_config({"nest_id":"local-nest","bed_count":32,"world_revision":1})
 if not check(bool(config.get("accepted",false)), "World did not configure"): return
 var trajectory := ARRIVAL.new()
 if not check(trajectory.bind(nest), "Actual fourth-floor arrival path not found"): return
 if not check(trajectory.walk_profile.size() == 67, "Walk-down path must follow real treads"): return
 var characters := Node3D.new()
 root.add_child(characters)
 var controller := CONTROLLER.new()
 root.add_child(controller)
 controller.setup(nest,characters,{"saevi":SAEVI},true)
 var data := {"actor_id":"resident","species":"saevi","appearance":{},"spawn_anchor_id":"dorm-01/bed-01","hosted":false,"arrival_id":"admission-one","arrival_started_at":Time.get_unix_time_from_system()-20.0}
 if not check(bool(controller.sync_actors([data]).get("accepted", false)), "Admission actor rejected"): return
 var body: ElfieActor = controller.actor("resident")
 if not check(body.elfie_id == "resident" and not bool(body.get_meta("arrival_completed")), "Arrival lost real identity or completed early"): return
 if not check(body.global_position.y > 9.0, "Adoption must arrive on fourth floor"): return
 var events: Array[Dictionary] = []
 controller.runtime_event.connect(func(event_name: String,payload: Dictionary,_cause: String) -> void: events.append({"name":event_name,"payload":payload}))
 controller.execute_intent({"command_id":"early","actor_id":"resident","intent":"turn","angle_degrees":45.0})
 if not check(events.any(func(event: Dictionary) -> bool: return event.name == "intent_terminal" and event.payload.get("reason") == "virtual_body_unavailable"), "Brain command ran during arrival"): return
 controller._arrivals["resident"] = Time.get_unix_time_from_system()-30.0
 controller._process(0.0)
 if not check(bool(body.get_meta("arrival_completed")) and controller._arrivals.is_empty(), "Arrival did not settle once"): return
 var settled := body.global_position
 controller.sync_actors([data])
 if not check(controller.actor("resident") == body and body.global_position == settled, "Duplicate admission restarted arrival"): return
 # Physical completion of an own-bed action is the precondition for hosting.
 var bed := nest.resolve_anchor("dorm-01/bed-01")
 body.global_position = bed.global_position
 if not check(body.enter_furniture(bed,"dorm-01/bed-01").is_empty(), "Own-bed furniture pose failed"): return
 data["hosted"] = true
 controller.sync_actors([data])
 if not check(controller.actor("resident") == body and body.furniture_anchor_id == "dorm-01/bed-01" and body.runtime_posture() == "sleeping", "Hosting removed or replaced sleeping body"): return
 data["hosted"] = false
 data["arrival_started_at"] = Time.get_unix_time_from_system()-120.0
 controller.sync_actors([data])
 if not check(controller.actor("resident") == body and body.furniture_anchor_id.is_empty(), "Return did not restore standing virtual body"): return
 # Observer uses the same resident identity and the authored bed shell.
 body.set_meta("observer_presentation",true)
 var effects := PRESENTATION.new()
 body.add_child(effects)
 effects.setup(nest,body)
 var entity := {"hosted":true,"home_anchor_id":"dorm-01/bed-01","arrival_id":null,"arrival_started_at":null}
 effects.apply(entity)
 if not check(effects.find_child("GlassDome",true,false) != null and body.visible and body.elfie_id == "resident", "Hosted presentation lacks fitted cover or visible body"): return
 entity["hosted"] = false
 effects.apply(entity)
 if not check(effects.find_child("GlassDome",true,false) == null, "Return left hosted cover behind"): return
 # No resident permission gates: every physical entry follows one world phase.
 body.global_position = Vector3(100,50,100)
 var physics: Node3D = nest.get("_estate_physics")
 nest.apply_environment_state("nest/environment",true,true,"day")
 physics.call("_physics_process",0.5)
 for door: Dictionary in physics.get("_doors"):
  if not check(is_equal_approx(float(door.amount),1.0), "Daytime entry not default open"): return
 nest.apply_environment_state("nest/environment",true,true,"night")
 physics.call("_physics_process",3.0)
 for door: Dictionary in physics.get("_doors"):
  if not check(is_zero_approx(float(door.amount)), "Night entry did not resume proximity policy"): return
 characters.free()
 controller.free()
 nest.free()
 print("PASS resident lifecycle: one-way adoption, identity/duplicate handling, hosted bed/cover/return and independent day/night doors")
 quit()
