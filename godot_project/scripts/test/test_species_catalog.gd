extends SceneTree

const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")


func _init() -> void:
	var catalog := SPECIES_CATALOG.discover_actor_scenes()
	for species_id: String in ["fox", "dog", "cat"]:
		if not catalog.has(species_id) or not catalog[species_id] is PackedScene:
			push_error("Discovered actor catalog is missing %s" % species_id)
			quit(1)
			return
	if catalog.size() < 3:
		push_error("Discovered actor catalog has fewer than three species")
		quit(1)
		return
	print("Dynamic species catalog contract passed: %s" % ", ".join(catalog.keys()))
	quit()
