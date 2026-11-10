@tool
extends Node3D
## Bind the shared split placements to the existing physical and presentation owners.
const LIVE_LIGHTING := preload("res://nest/estate/estate_lighting.gd")
const ACTIVITY := preload("res://nest/assembly/activity_regions.tres")
const BINDINGS := "res://nest/assembly/runtime-bindings.json"
var restored_controls := {"lights": 0, "emission": 0}

func binding_key(node: Node) -> String:
	return str(get_path_to(node))

func _ready() -> void:
	restored_controls = {"lights": 0, "emission": 0}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(BINDINGS))
	if not data is Dictionary or not data.has("placements") or not data.has("lighting"):
		push_error("Missing split runtime bindings")
		return
	for node: Node in find_children("*", "", true, false):
		if str(node.name).begins_with("@"): node.name = "RuntimeNode_%d" % node.get_index()
		if node.has_meta("source_geometry_path"): continue
		var path := str(node.get_meta("v044_path", ""))
		if path.is_empty(): continue
		var original := path.get_slice("/Region_", 0).get_file()
		var extras: Dictionary = data.placements.get(path.get_slice("/Region_", 0), {}).duplicate(true)
		extras["source_name"] = extras.get("source_name", original)
		var module := ""
		var context := node.get_parent()
		while context != null:
			if context.has_meta("estate_module"):
				module = str(context.get_meta("estate_module"))
				break
			context = context.get_parent()
		if module.is_empty(): module = ACTIVITY.module_of(node)
		if not module.is_empty(): extras["module"] = module
		node.set_meta("extras", extras)
		if not original.begins_with("@") and not original.is_empty(): node.name = original
	restore_lighting(data.lighting)
	set_meta("runtime_bindings", restored_controls.duplicate())
	var ready: bool = restored_controls.lights == find_children("*", "Light3D", true, false).size() and restored_controls.emission == data.lighting.emission.size()
	set_meta("split_runtime_ready", ready)
	if not ready: push_error("Incomplete split lighting/emission bindings")

func ownership_extras(group: String, previous: Dictionary) -> Dictionary:
	var e:=previous.duplicate(true)
	if group.begins_with("central-"):
		e["module"]="central"
		e["floor"]=int(group.trim_prefix("central-"))
	elif group.begins_with("dorm-"):e["module"]="M%02d"%int(group.trim_prefix("dorm-"))
	elif group=="outdoor":e["outdoor_fixture_id"]=e.get("outdoor_fixture_id","retained-fixture")
	return e

func restore_lighting(controls: Dictionary) -> void:
	for node: Node in find_children("*", "", true, false):
		if node.has_meta("source_geometry_path"): continue
		var path := binding_key(node)
		if node is Light3D:
			var data: Dictionary = controls.lights.get(path, {})
			if data.is_empty():
				push_error("Missing split light control: " + path)
				continue
			node.light_energy = float(data.energy)
			node.light_cull_mask = int(data.mask)
			node.visible = bool(data.visible)
			node.set_meta("estate_initial_energy", float(data.energy))
			# The saved scene owns authored availability; visible is only the
			# captured day/night state (calibrated bedroom ceilings start off).
			if not node.has_meta(LIVE_LIGHTING.INITIAL_VISIBLE):
				node.set_meta(LIVE_LIGHTING.INITIAL_VISIBLE, bool(data.visible))
			node.set_meta("extras", ownership_extras(str(data.group), node.get_meta("extras", {})))
			restored_controls.lights += 1
		if node is MeshInstance3D and node.mesh != null:
			for surface: int in node.mesh.get_surface_count():
				var key := path + ":" + str(surface)
				if not controls.emission.has(key): continue
				var material := node.get_active_material(surface) as BaseMaterial3D
				if material == null: continue
				var energy := float(controls.emission[key].energy)
				var owned := material.duplicate() as BaseMaterial3D
				owned.emission_energy_multiplier = energy
				owned.set_meta(LIVE_LIGHTING.INITIAL_EMISSION, energy)
				LIVE_LIGHTING.set_material(node, surface, owned)
				restored_controls.emission += 1

	# Render partitions are disposable draw instances of the same source surface.
	# They must start from its restored state, not the frozen imported day state.
	for chunk: MeshInstance3D in find_children("*", "MeshInstance3D", true, false):
		if not chunk.has_meta("source_geometry_path"): continue
		var source := chunk.get_parent().get_parent() as MeshInstance3D
		var surface := int(chunk.get_meta("source_surface"))
		LIVE_LIGHTING.set_material(chunk, 0, source.get_active_material(surface))
