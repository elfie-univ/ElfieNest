extends SceneTree
## The imported scene must share identical buffers before runtime allocation.
func _initialize() -> void:
	var before := OS.get_static_memory_usage()
	var scene := load("res://rooms/estate/ElfieNest-complete-final.glb") as PackedScene
	var bytes := OS.get_static_memory_usage()-before
	print("IMPORTED_ESTATE_MEMORY bytes=",bytes)
	if scene==null or bytes>=700000000:
		push_error("Imported complete estate must stay below 700 MB before instantiation")
		quit(1)
		return
	print("PASS complete imported estate memory")
	quit()
