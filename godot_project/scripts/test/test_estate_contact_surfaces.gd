extends SceneTree
## Verify the imported display meshes, not only the source GLB measurements.

func _initialize() -> void: call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
	root.add_child(estate)
	var shelf := estate.find_child("Draft L2 curved bookcase continuous hidden diffuser",true,false) as MeshInstance3D
	if not require((shelf.global_transform*shelf.get_aabb()).end.y < 4.701,"Imported shelf lamp must expose the latest repaired lens below the timber"): return
	var desk := estate.find_child("Draft L3 writing desk concealed downward task lens",true,false) as MeshInstance3D
	var desk_box := desk.global_transform*desk.get_aabb()
	if not require(desk_box.size.y > 0.02 and desk_box.position.x > 7.77,"Imported writing lamp must be vertical on its backboard"): return
	var chair := estate.find_child("quiet_rear_reading_armchair",true,false) as MeshInstance3D
	var seat: PackedVector3Array = chair.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var legs: PackedVector3Array = chair.mesh.surface_get_arrays(1)[Mesh.ARRAY_VERTEX]
	var seat_bottom := INF
	var leg_top := -INF
	for point: Vector3 in seat: seat_bottom=minf(seat_bottom,point.y)
	for point: Vector3 in legs: leg_top=maxf(leg_top,point.y)
	if not require(leg_top>seat_bottom+0.002,"Imported reading-chair legs must actually reach the seat"): return
	var easel := estate.find_child("botanical_painting_easel",true,false) as MeshInstance3D
	# A tilted object's transformed AABB includes empty corners below its feet.
	# Measure the actual imported vertices in the room frame instead.
	var easel_bottom := INF
	for surface in range(easel.mesh.get_surface_count()):
		var points: PackedVector3Array = easel.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
		for point: Vector3 in points: easel_bottom=minf(easel_bottom,(easel.global_transform*point).y)
	if not require(easel_bottom > 3.12 and easel_bottom < 3.135,"Imported easel feet must meet the actual terrace rug instead of floating above it"): return
	var throw_mesh := estate.find_child("linen_throw_on_fitted_sofa",true,false) as MeshInstance3D
	if not require(throw_mesh.get_aabb().end.z < 0.60,"Imported M01 cloth must occupy the free gap between its cushions"): return
	var bedroom_lamps := 0
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		var e: Dictionary=mesh.get_meta("extras",{})
		if e.get("source_name","")=="Desk | amber globe":
			bedroom_lamps+=1
			if not require((mesh.global_transform*mesh.get_aabb()).size.y>0.18,"All imported desk globes must use the enlarged shared model"): return
	if not require(bedroom_lamps==32,"Retain all thirty-two bedroom desk lamps"): return
	print("PASS imported current contact repairs: supported reading chair, fitted writing lamp, exposed bookcase lamp, 32 enlarged desk lamps")
	estate.free()
	quit(0)
