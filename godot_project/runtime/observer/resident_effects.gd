extends Node3D
## Read-only presentation of committed admission and hosted-bed facts.
const EFFECTS := preload("res://nest/rendering/estate_event_effects.gd")
const CYCLE := preload("res://nest/buildings/main/arrival/estate_platform_cycle.gd")
const LIGHTING := preload("res://nest/buildings/main/arrival/estate_arrival_lighting.gd")
var _nest: ModularNest
var _body: ElfieActor
var _facts: Dictionary = {}
var _cover: Node3D
var _arrival: Node3D
var _cycle: Node3D
var _lighting: Node3D
var _completed_id := ""
var _was_hosted := false
var _collision_disabled := false

func setup(nest: ModularNest, body: ElfieActor) -> void:
 _nest = nest
 _body = body
 top_level = true
 global_transform = Transform3D.IDENTITY

func apply(entity: Dictionary) -> bool:
 _facts = entity.duplicate(true)
 var hosted := bool(entity.get("hosted", false))
 if hosted:
  _finish_arrival()
  if not _was_hosted:
   _body.observer_stop_presentation()
   var bed := _nest.resolve_anchor(String(entity["home_anchor_id"]))
   _body.global_position = bed.global_position
   _body.observer_present_anchor(bed, String(entity["home_anchor_id"]), "sleeping")
   _body.visible = true
   _build_cover(bed)
  _was_hosted = true
  return true
 if _was_hosted:
  _was_hosted = false
  if is_instance_valid(_cover): _cover.free()
  _cover = null
  _body.observer_stop_presentation()
 var started: Variant = entity.get("arrival_started_at")
 var event_id := String(entity.get("arrival_id", "")) if entity.get("arrival_id") != null else ""
 if started == null or event_id == _completed_id: return false
 var elapsed := Time.get_unix_time_from_system() - float(started)
 if elapsed >= CYCLE.SETTLED_AT:
  _completed_id = event_id
  _finish_arrival()
  return false
 if _cycle == null: _build_arrival()
 if _cycle == null: return true
 _cycle.call("sample", elapsed)
 return true

func _process(_delta: float) -> void:
 if _nest == null or _nest.observer_presentation_paused(): return
 if _cycle != null:
  var elapsed := Time.get_unix_time_from_system() - float(_facts["arrival_started_at"])
  _cycle.call("sample", elapsed)
  if elapsed >= CYCLE.SETTLED_AT:
   _completed_id = String(_facts["arrival_id"])
   _finish_arrival()

func _build_cover(bed: Marker3D) -> void:
 var source := _nest.find_child(String(bed.get_meta("source_node", "")), true, false)
 if source == null: return
 var extras := source.get_meta("extras", {}) as Dictionary
 var shell: MeshInstance3D
 var parts: Array[MeshInstance3D] = []
 for mesh: MeshInstance3D in _nest.find_children("*", "MeshInstance3D", true, false):
  var e := mesh.get_meta("extras", {}) as Dictionary
  if e.get("module") != extras.get("module") or e.get("resident") != extras.get("resident") or e.get("assembly") != "bed": continue
  if e.get("piece") in ["shell", "rolled_lip", "deck"]: parts.append(mesh)
  if e.get("piece") == "shell": shell = mesh
 if shell == null: return
 var points := PackedVector3Array()
 var crown := PackedVector3Array()
 for part: MeshInstance3D in parts:
  var frame := shell.global_transform.affine_inverse() * part.global_transform
  for surface in range(part.mesh.get_surface_count()):
   var vertices: PackedVector3Array = part.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
   for vertex: Vector3 in vertices:
    points.append(frame * vertex)
    if (part.get_meta("extras", {}) as Dictionary).get("piece") == "rolled_lip": crown.append(frame * vertex)
 _cover = EFFECTS.new()
 add_child(_cover)
 _cover.call("configure_bed", shell.global_transform, shell.get_aabb(), points, crown)
 _cover.call("preview_cover", 3.5)

func _build_arrival() -> void:
 var platform: MeshInstance3D
 var stairs: MeshInstance3D
 var floor_mesh: MeshInstance3D
 for mesh: MeshInstance3D in _nest.find_children("*", "MeshInstance3D", true, false):
  if String(mesh.name).begins_with("Roof01 complete raised landing platform"): platform = mesh
  elif String(mesh.name) == "Roof01 two rear fan steps": stairs = mesh
  elif String(mesh.name).begins_with("Central L4 round arrival floor"): floor_mesh = mesh
 if platform == null or stairs == null or floor_mesh == null: return
 _body.observer_stop_presentation()
 var bounds := platform.global_transform * platform.get_aabb()
 _arrival = EFFECTS.new()
 add_child(_arrival)
 _arrival.call("configure_arrival", Vector3(bounds.get_center().x, bounds.end.y+0.025, bounds.get_center().z), minf(1.1, minf(bounds.size.x,bounds.size.z)*0.25))
 _lighting = _nest.get_node_or_null("ResidentArrivalLighting") as Node3D
 if _lighting == null:
  _lighting = LIGHTING.new()
  _lighting.name = "ResidentArrivalLighting"
  _nest.add_child(_lighting)
  _lighting.call("bind", _nest)
 _cycle = CYCLE.new()
 add_child(_cycle)
 _collision_disabled = (_body.get_node("CollisionShape3D") as CollisionShape3D).disabled
 # Bind derives facing from the current body position; establish the platform
 # origin first so a resident downstairs cannot acquire a pitched orientation.
 _body.global_position = Vector3(bounds.get_center().x, bounds.end.y+0.02, bounds.get_center().z)
 var surfaces: Array[MeshInstance3D] = [platform, stairs, floor_mesh]
 _cycle.call("bind", _arrival, bounds, Callable(_lighting, "sample"), (stairs.global_transform*stairs.get_aabb()).get_center(), surfaces, _body, true)

func _finish_arrival() -> void:
 if _cycle != null:
  _cycle.call("sample", CYCLE.SETTLED_AT)
  _cycle.free()
  _cycle = null
  (_body.get_node("CollisionShape3D") as CollisionShape3D).disabled = _collision_disabled
 if _arrival != null:
  _arrival.free()
  _arrival = null
 if _lighting != null:
  _lighting.call("sample", CYCLE.IDLE_SECONDS)
  _lighting = null
