extends Node
## Runs short repeatable demonstrations through the normal actor controller.
const PLANS := preload("res://runtime/actor/demonstration_plans.gd")
const ITEMS := [
 ["morning","日常生活","早晨起床·二楼一圈"], ["evening","日常生活","大厅巡检·晚上入睡"],
 ["ring","环境巡检","建筑环线"], ["forest","环境巡检","林间小路一圈"], ["lake","环境巡检","湖边广场一圈"],
 ["arrival","到达与招呼","顶楼到一楼·挥手"], ["seats","家具巡检","主楼沙发多座位"]]
var controller: Node
var nest: ModularNest
var _tokens: Dictionary = {}
var _commands: Dictionary = {}
var _results: Dictionary = {}
var _sequence := 0
var states: Dictionary = {}
var _catalog_cache: Dictionary = {}
var _catalog_iteration := -1
var _requests: Dictionary = {}

func setup(world: ModularNest, actor_controller: Node) -> void:
 nest=world
 controller=actor_controller
 controller.runtime_event.connect(_event)

func catalog(actor_id: String) -> Array[Dictionary]:
 var items: Array[Dictionary]=[]
 var bed: String = controller.home_anchor_for(actor_id)
 var iteration := NavigationServer3D.map_get_iteration_id(nest.get_world_3d().navigation_map)
 if iteration != _catalog_iteration:
  _catalog_cache.clear()
  _catalog_iteration=iteration
 if _catalog_cache.has(bed): return _catalog_cache[bed]
 for item: Array in ITEMS:
  var route := PLANS.points(nest,item[0],bed)
  items.append({"id":item[0],"group":item[1],"label":item[2],"available":route.size()>1})
 _catalog_cache[bed]=items
 return items

func running(actor_id: String) -> bool: return _tokens.has(actor_id)

func cancel(actor_id: String) -> void:
 _requests.erase(actor_id)
 if not running(actor_id): return
 _tokens[actor_id] = -1
 var body := controller.actor(actor_id) as ElfieActor
 if body == null: return
 var command := str(_commands.get(actor_id,body.furniture_cycle_command if not body.furniture_cycle_command.is_empty() else body.active_command_id))
 if not command.is_empty(): controller.cancel_intent({"command_id":command,"actor_id":actor_id})

func play(actor_id: String, id: String) -> void:
 cancel(actor_id)
 _sequence+=1
 var request := _sequence
 _requests[actor_id]=request
 while running(actor_id):
  await get_tree().physics_frame
  if _requests.get(actor_id)!=request:return
 if _requests.get(actor_id)!=request:return
 var body := controller.actor(actor_id) as ElfieActor
 if body == null: return
 _sequence+=1
 var token := _sequence
 _tokens[actor_id]=token
 states[actor_id]="准备演示"
 var deadline := Time.get_ticks_msec()+3000
 while not body.active_command_id.is_empty() or not body.furniture_cycle_command.is_empty():
  var previous := body.furniture_cycle_command if not body.furniture_cycle_command.is_empty() else body.active_command_id
  controller.cancel_intent({"command_id":previous,"actor_id":actor_id})
  await get_tree().physics_frame
  if Time.get_ticks_msec()>deadline: _finish(actor_id,"取消旧动作超时"); return
 var bed: String = controller.home_anchor_for(actor_id)
 var route := PLANS.points(nest,id,bed)
 if route.size()<2: _finish(actor_id,"路线不可通行，未开始演示"); return
 if not body.leave_furniture(): _finish(actor_id,"无法离开家具"); return
 body.global_position=route[0]
 body.velocity=Vector3.ZERO
 if id == "morning":
  body.set_meta("preview_sleep_start",11.0)
  var woke := await _intent(actor_id,token,{"intent":"use_anchor","anchor_id":bed,"furniture_cycle":"sleep-back"})
  if is_instance_valid(body): body.remove_meta("preview_sleep_start")
  if not woke: return
 if id == "seats":
  if not await _intent(actor_id,token,{"intent":"use_anchor","anchor_id":"central-01/sofa-left","furniture_cycle":"seat"}): return
 for index in range(1,route.size()):
  if _tokens.get(actor_id)!=token: _finish(actor_id,"已取消"); return
  states[actor_id]="%s · %d/%d" % [id,index,route.size()-1]
  if id == "seats":
   var anchor: String = ["central-01/sofa-left","central-01/sofa","central-01/sofa-right"][index]
   if not await _intent(actor_id,token,{"intent":"use_anchor","anchor_id":anchor,"furniture_cycle":"seat"}): return
  else:
   # The same movement and collision implementation as move-to-anchor.
   var marker := Marker3D.new()
   nest.add_child(marker)
   marker.global_position=route[index]
   var anchor := "demo/%s/%d" % [actor_id,index]
   nest._anchor_markers[anchor]=marker
   var ok := await _intent(actor_id,token,{"intent":"move_to_anchor","anchor_id":anchor})
   nest._anchor_markers.erase(anchor)
   marker.queue_free()
   if not ok: return
 if id == "evening":
  if not await _intent(actor_id,token,{"intent":"use_anchor","anchor_id":bed,"furniture_cycle":"sleep-back"}): return
 if id == "arrival":
  if not await _intent(actor_id,token,{"intent":"emotion_expression","expression":"pose_waving"}): return
  await get_tree().create_timer(1.5).timeout
 _finish(actor_id,"演示完成")

func _intent(actor_id: String, token: int, fields: Dictionary) -> bool:
 if _tokens.get(actor_id)!=token: _finish(actor_id,"已取消"); return false
 _sequence+=1
 var id := "demo-%d" % _sequence
 var payload := {"command_id":id,"intent_id":id,"actor_id":actor_id,"body_generation":1,"initiator":"elfie","deadline_seconds":120.0}
 payload.merge(fields)
 _commands[actor_id]=id
 controller.execute_intent(payload)
 var deadline := Time.get_ticks_msec()+125000
 while not _results.has(id):
  await get_tree().physics_frame
  if controller.actor(actor_id)==null: _finish(actor_id,"精灵已移除"); return false
  if Time.get_ticks_msec()>deadline:
   controller.cancel_intent({"command_id":id,"actor_id":actor_id})
   _finish(actor_id,"动作执行超时"); return false
 var result: Dictionary=_results[id]
 _results.erase(id)
 if _tokens.get(actor_id)!=token or result.get("status")!="completed":
  _finish(actor_id,"已取消" if _tokens.get(actor_id)!=token else str(result.get("reason","动作失败"))); return false
 return true

func _event(name: String, payload: Dictionary, _cause: String) -> void:
 if name=="intent_terminal" and str(payload.get("command_id","")).begins_with("demo-"): _results[str(payload.command_id)]=payload

func _finish(actor_id: String, message: String) -> void:
 _results.erase(str(_commands.get(actor_id,"")))
 _tokens.erase(actor_id)
 _commands.erase(actor_id)
 states[actor_id]=message
