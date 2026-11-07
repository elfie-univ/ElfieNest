extends RefCounted
## Physical, non-looping arrival trajectory sampled from the actual platform colliders.
const TIMING := preload("res://nest/estate/estate_platform_cycle.gd")
var origin := Vector3.ZERO
var steps := Vector3.ZERO
var platform_bounds := AABB()
var walk_profile: Array[Vector3] = []

func bind(nest: ModularNest) -> bool:
 var marker := nest.resolve_anchor("central-04/activity")
 if marker == null: return false
 var faces := PackedVector3Array()
 var platform := PackedVector3Array()
 var stairs := PackedVector3Array()
 for body: StaticBody3D in nest.find_children("*", "StaticBody3D", true, false):
  var label := String(body.get_meta("source_node", ""))
  if not (label.begins_with("Roof01 complete raised landing platform") or label.begins_with("Central L4 round arrival floor") or label == "Roof01 two rear fan steps"): continue
  for shape: CollisionShape3D in body.find_children("*", "CollisionShape3D", true, false):
   if not shape.shape is ConcavePolygonShape3D: continue
   var local := (shape.shape as ConcavePolygonShape3D).get_faces()
   var world := PackedVector3Array()
   for point: Vector3 in local: world.append(shape.global_transform * point)
   faces.append_array(world)
   if label.begins_with("Roof01 complete raised landing platform"): platform.append_array(world)
   elif not label.begins_with("Central L4"): stairs.append_array(world)
 if platform.is_empty() or stairs.is_empty(): return false
 platform_bounds = AABB(platform[0], Vector3.ZERO)
 for point: Vector3 in platform: platform_bounds = platform_bounds.expand(point)
 var step_bounds := AABB(stairs[0], Vector3.ZERO)
 for point: Vector3 in stairs: step_bounds = step_bounds.expand(point)
 steps = step_bounds.get_center()
 origin = Vector3(marker.global_position.x, platform_bounds.end.y + 0.025, marker.global_position.z)
 walk_profile = sample_walk(origin, steps, faces)
 return walk_profile.size() == 67

static func sample_walk(start: Vector3, stairs: Vector3, triangles: PackedVector3Array) -> Array[Vector3]:
 var result: Array[Vector3] = []
 var heading := stairs - start
 heading.y = 0
 heading = heading.normalized()
 for index in range(67):
  var point := start + heading * (3.3 * float(index) / 66.0)
  var top := -INF
  for face in range(0, triangles.size(), 3):
   var hit: Variant = Geometry3D.ray_intersects_triangle(point + Vector3.UP, Vector3.DOWN, triangles[face], triangles[face+1], triangles[face+2])
   if hit != null: top = maxf(top, (hit as Vector3).y)
  if not is_finite(top): return []
  point.y = top + 0.02
  result.append(point)
 return result

func sample(actor: ElfieActor, seconds: float) -> void:
 var time := clampf(seconds, 0.0, TIMING.SETTLED_AT)
 var local := maxf(0.0, time - TIMING.PREPARE_SECONDS)
 var progress := smoothstep(3.0, 5.6, local)
 actor.global_position = origin + Vector3.UP * ((1.0-progress)*0.9)
 if time >= TIMING.WALK_START:
  var distance := clampf((time - TIMING.WALK_START)/6.0, 0.0, 1.0) * float(walk_profile.size()-1)
  var index := mini(int(distance), walk_profile.size()-2)
  actor.global_position = walk_profile[index].lerp(walk_profile[index+1], distance-float(index))
 actor.visible = progress > 0.001
 var facing := steps
 facing.y = actor.global_position.y
 actor.look_at(facing, Vector3.UP, true)
 actor.call("_play_animation", "walking" if time >= TIMING.WALK_START and time < TIMING.SETTLED_AT else "idle")
 actor.velocity = Vector3.ZERO
