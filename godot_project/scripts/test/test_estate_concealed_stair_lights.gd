extends SceneTree
const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")

func _initialize() -> void:
	call_deferred("run")

func require(ok: bool, message: String) -> bool:
	if not ok:
		push_error(message)
		quit(1)
	return ok

func run() -> void:
	var estate: Node3D=load("res://rooms/estate/ElfieNest-complete-final.glb").instantiate()
	root.add_child(estate)
	DAYLIGHT.apply(estate)
	var emitters := 0
	var shields := 0
	for mesh: MeshInstance3D in estate.find_children("*","MeshInstance3D",true,false):
		var extra: Dictionary=mesh.get_meta("extras",{})
		if extra.get("lighting_kind")!="stair" or extra.get("stair_edge_role")!="side": continue
		var lights: Array=extra.get("design_lights",[])
		if lights.is_empty():
			shields+=1
			if not require(mesh.visible and mesh.layers!=0,"Concealed stair shielding must remain visible"): return
			continue
		emitters+=1
		if not require(mesh.layers==0,"Concealed sloping light geometry must not protrude visibly through a stair cheek wall: "+str(mesh.name)): return
		if not require(mesh.visible,"Keep emitter owner visible so its actual lights remain active"): return
		# Godot renames repeated siblings added without force_readable_name.
		var actual_lights := mesh.find_children("*","Light3D",false,false)
		if not require(actual_lights.size()==lights.size(),"Hiding the emitter surface must preserve every authored stair light"): return
		for light: Light3D in actual_lights:
			if not require(light.visible and light.light_energy>0.0,"Indirect stair illumination must remain enabled"): return
	if not require(emitters==6 and shields==6,"Expected inner/outer concealed strips and shields on all three stair flights"): return
	estate.free()
	await process_frame
	print("PASS concealed stairs: six bright source surfaces hidden, six shields and eighteen real light sources preserved")
	quit(0)
