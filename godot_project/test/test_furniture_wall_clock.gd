extends SceneTree
## Slow presentation must not stretch a safe, subdivided chair turn.
class Carrier extends "res://runtime/actor/chair_swivel.gd":
 var headings: Array[float] = []
 func _clear(target: Transform3D, _passenger: CharacterBody3D) -> bool:
  headings.append(target.basis.get_euler().y)
  return true
func _initialize() -> void: call_deferred("run")
func run() -> void:
 var previous_fps := Engine.max_fps
 var previous_steps := Engine.max_physics_steps_per_frame
 Engine.max_fps = 10
 Engine.max_physics_steps_per_frame = 1
 var carrier := Carrier.new()
 root.add_child(carrier)
 var start := Time.get_ticks_usec()
 var ok := await carrier.turn_to(0.325, null)
 var seconds := float(Time.get_ticks_usec()-start)/1000000.0
 Engine.max_fps = previous_fps
 Engine.max_physics_steps_per_frame = previous_steps
 var maximum := 0.0
 var previous := 0.0
 for heading in carrier.headings:
  maximum = maxf(maximum,absf(heading-previous))
  previous = heading
 var passed := ok and seconds < 1.25 and maximum < 0.017 and is_equal_approx(carrier.rotation.y,0.325)
 print("CHAIR_CLOCK seconds=",seconds," collision_samples=",carrier.headings.size()," maximum_angle=",maximum)
 carrier.free()
 if not passed: push_error("Low frame rate stretched the chair turn or skipped collision subdivisions")
 quit(0 if passed else 1)
