extends SceneTree
## Add the display-free snapshot without rebaking unchanged collision/navigation.
const DATA := preload("res://rooms/estate/estate_spatial_data.gd")
const COMPILER := preload("res://rooms/estate/estate_authority_scene.gd")
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
func _initialize() -> void:call_deferred("run")
func run() -> void:
 var data := load(DATA.PATH) as Resource
 if not data.matches_inputs(DATA.current_inputs()):
  push_error("Compile the matching estate spatial data first");quit(1);return
 var world := Node3D.new()
 root.add_child(world)
 var estate := load("res://rooms/estate/estate.tscn").instantiate() as Node3D
 world.add_child(estate)
 var physics := PHYSICS.new()
 world.add_child(physics)
 physics.build(estate)
 data.authority_scene=COMPILER.capture(world,estate,physics)
 data.authority_format_version=DATA.AUTHORITY_FORMAT_VERSION
 var output := ProjectSettings.globalize_path("res://../build/estate_spatial")
 DirAccess.make_dir_recursive_absolute(output)
 if ResourceSaver.save(data,output.path_join("estate_spatial.res"),ResourceSaver.FLAG_COMPRESS)!=OK:
  push_error("Could not save physical authority snapshot");quit(1);return
 print("PASS compiled display-free authority from complete world; collision and navigation resources preserved")
 world.free()
 quit()
