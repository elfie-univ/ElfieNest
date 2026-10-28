extends SceneTree
const CHARGE := preload("res://runtime/lab/estate_petal_charge.gd")
const TIMING := preload("res://runtime/lab/estate_platform_cycle.gd")

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func snapshot(charge: Node3D) -> Array:
	var result := []
	for item: Dictionary in charge.get("shells"):
		result.append([item["mesh"].global_transform,item["inlay"].get_shader_parameter("fill"),item["inlay"].get_shader_parameter("level"),item["material"].get_shader_parameter("fill"),item["material"].get_shader_parameter("level")])
	for item: Dictionary in charge.get("rear_lights"):
		result.append([item["mesh"].global_transform,item["material"].get_shader_parameter("fill"),item["material"].get_shader_parameter("level")])
	return result

func run() -> void:
	var geometry: Node3D=load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(geometry)
	var charge := CHARGE.new()
	root.add_child(charge)
	charge.bind(geometry,{})
	charge.sample(0.0)
	var opening := snapshot(charge)
	if not require(opening.size()==6,"Expected three real petal faces and three original rear lines"): return
	charge.sample(8.2)
	if not require(float(charge.shells[0]["inlay"].get_shader_parameter("level"))>0.5,"The test must visit the charged state before checking restoration"): return
	charge.sample(TIMING.REVIEW_END)
	if not require(snapshot(charge)==opening,"Completed animation must restore the opening surface colors, light levels and transforms"): return
	charge.sample(TIMING.IDLE_SECONDS)
	if not require(snapshot(charge)==opening,"Idle state must match the opening state even after seeking"): return
	charge.sample(0.0)
	if not require(snapshot(charge)==opening,"Replay must start from the same restored state"): return
	charge.free()
	geometry.free()
	await process_frame
	print("PASS arrival idle: real petal faces/rear lines restore opening colors, levels and transforms after completion, seek and replay")
	quit(0)
