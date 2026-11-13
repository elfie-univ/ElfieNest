extends SceneTree

func _initialize() -> void:
	var shore := preload("res://nest/courtyard/parts/waterside/estate_shore_finish.gd").new()
	shore.water = PackedVector2Array([Vector2(-1,-1), Vector2(1,-1), Vector2(1,1), Vector2(-1,1)])
	shore.water_bounds = Rect2(-1,-1,2,2)
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.10,0.10,0.10)
	var material := StandardMaterial3D.new()
	material.resource_name = "Layered low groundcover test"
	mesh.material = material
	# This tuft is entirely outside the 17 cm landward edge of the lamp.
	var buffer := PackedFloat32Array([1,0,0,1.25, 0,1,0,0, 0,0,1,0])
	shore.retreat_plants(mesh,buffer)
	if absf(buffer[3] - 1.25) > 0.001:
		push_error("Do not push valid bank plants back and create a bare green band")
		quit(1)
		return
	print("PASS: bank plants remain beside the real lamp footprint")
	quit(0)
