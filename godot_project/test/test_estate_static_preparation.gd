extends SceneTree
## Frozen geometry corrections must be idempotent and stored by the importer.
const SURFACE := preload("res://nest/estate/estate_surface.gd")

func _initialize() -> void:call_deferred("run")

func run() -> void:
	var source := load("res://nest/estate/ElfieNest-complete-final.glb").instantiate() as Node3D
	root.add_child(source)
	var windows := {}
	var checked := 0
	for node: MeshInstance3D in source.find_children("*","MeshInstance3D",true,false):
		var extras: Dictionary=node.get_meta("extras",{})
		var original:=node.mesh
		if extras.get("source_name","")=="ROOM • front fitted deep reveal":
			if not original.get_meta("estate_window_normals",false):fail("Window correction was not imported");return
			SURFACE.repair_window_normals(node,windows)
			if node.mesh!=original:fail("Window correction allocated again at runtime");return
			checked+=1
		if extras.get("piece","")=="bed_cover":
			if not original.get_meta("estate_duvet_rest",false) or SURFACE.duvet_rest(original)!=original:fail("Bedding rest geometry was rebuilt at runtime");return
			checked+=1
	if checked==0:fail("No static corrections checked");return
	print("ESTATE_STATIC_PREPARATION checked=",checked," failures=0")
	source.free();quit()

func fail(message: String) -> void:
	push_error(message);quit(1)
