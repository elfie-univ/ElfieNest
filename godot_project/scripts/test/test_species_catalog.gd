extends SceneTree

const SPECIES_CATALOG := preload("res://runtime/species_catalog.gd")


func _init() -> void:
	var catalog := SPECIES_CATALOG.discover_actor_scenes()
	for species_id: String in ["fox", "dog"]:
		if not catalog.has(species_id) or not catalog[species_id] is PackedScene:
			push_error("Discovered actor catalog is missing %s" % species_id)
			quit(1)
			return
	if catalog.size() != 2 or catalog.has("cat"):
		push_error("Discovered actor catalog contains an incomplete species")
		quit(1)
		return
	for species_id: String in ["fox", "dog"]:
		var validation := SPECIES_CATALOG.validate_species_package(species_id)
		if not bool(validation.get("accepted", false)):
			push_error("Species package validation failed for %s: %s" % [species_id, validation])
			quit(1)
			return
	var incomplete := SPECIES_CATALOG.validate_species_package("cat")
	if bool(incomplete.get("accepted", true)) or incomplete.get("code") != "missing_manifest":
		push_error("Incomplete species package was not rejected: %s" % [incomplete])
		quit(1)
		return
	print("Complete species catalog contract passed: %s" % ", ".join(catalog.keys()))
	quit()
