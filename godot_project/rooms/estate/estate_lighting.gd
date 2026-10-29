extends RefCounted
## Apply Nest's existing ordinary-light snapshot without owning time or status.

const DAYLIGHT := preload("res://rooms/estate/estate_daylight.gd")
const INITIAL_VISIBLE := &"estate_initial_light_visible"
const INITIAL_EMISSION := &"estate_initial_emission_energy"
# Source fixture materials whose names do not contain the existing authoring
# classifier's lamp/diffuser tokens. Screens, water and plant emission are separate.
const FIXTURE_EMISSION := [
	"Soft cyan frosted lens.001",
	"Honey translucent glass globe.001",
	"Globe soft honey filament.001",
	"L3 desk shielded 3000K task lens",
]
# These are part of the roof arrival apparatus, not room-light switches.
const ARRIVAL_EMISSION := [
	"Roof fine turquoise halo",
	"Roof01 pale aqua frosted landing disc.001",
	"Roof01 radial luminous crystal",
	"Roof01 cyan light channel.001",
]
var _lights: Array[Dictionary] = []
var _materials: Array[Dictionary] = []


func bind(nest: Node) -> Dictionary:
	_lights.clear()
	_materials.clear()
	var counts := {"artificial_lights": 0, "ordinary_emission": 0, "independent_emission": 0, "authored_bounce": 0}
	for light: Light3D in nest.find_children("*", "Light3D", true, false):
		if is_ordinary_light(light, nest):
			# CeilingFill survives Generated rebuilds. Capture its authored
			# visibility once, never the result of the last environment command.
			if not light.has_meta(INITIAL_VISIBLE):
				light.set_meta(INITIAL_VISIBLE, light.visible)
			if not light.has_meta("estate_initial_energy"): light.set_meta("estate_initial_energy",light.light_energy)
			_lights.append({"light": light, "visible": light.get_meta(INITIAL_VISIBLE),"energy":light.get_meta("estate_initial_energy"),"group":lighting_group(light)})
			counts["artificial_lights"] += 1
	var owned: Dictionary = {}
	var independent: Dictionary = {}
	for mesh: MeshInstance3D in nest.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		for surface in range(mesh.mesh.get_surface_count()):
			var original := mesh.get_active_material(surface) as BaseMaterial3D
			if original == null or not original.emission_enabled:
				continue
			if not is_ordinary_emission(original):
				if not independent.has(original.get_instance_id()):
					independent[original.get_instance_id()] = true
					var key := "authored_bounce" if DAYLIGHT._is_authored_bounce(original.resource_name.to_lower()) else "independent_emission"
					counts[key] += 1
				continue
			var group := lighting_group(mesh)
			var identity := "%d:%s"%[original.get_instance_id(),group]
			if not owned.has(identity):
				var material := original.duplicate() as BaseMaterial3D
				var energy := float(original.get_meta(INITIAL_EMISSION, original.emission_energy_multiplier))
				# Only tag this owned override; never write to an imported material.
				material.set_meta(INITIAL_EMISSION, energy)
				owned[identity] = material
				_materials.append({"material": material, "energy": energy,"group":group})
				counts["ordinary_emission"] += 1
			mesh.set_surface_override_material(surface, owned[identity])
	return counts


func apply(lights_on: bool, quiet_mode: bool = false, occupied: PackedStringArray = PackedStringArray(), usage_known: bool = false) -> void:
	for binding: Dictionary in _lights:
		var scale := group_scale(binding.group,lights_on,quiet_mode,occupied,usage_known)
		var light := binding.light as Light3D
		light.visible = scale>0.0 and bool(binding.visible)
		light.light_energy=float(binding.energy)*scale*light_boost(light, binding.group, quiet_mode)
	for binding: Dictionary in _materials:
		(binding.material as BaseMaterial3D).emission_energy_multiplier = group_scale(binding.group,lights_on,quiet_mode,occupied,usage_known)*emission_energy(binding.material, binding.energy, binding.group, quiet_mode)


static func lighting_group(node: Node) -> StringName:
	var current := node
	while current!=null:
		var e: Dictionary = current.get_meta("extras",{})
		if e.has("outdoor_fixture_id") or str(current.name)=="OutdoorLighting": return &"outdoor"
		var module := str(e.get("module",""))
		if module=="central":
			var zone := "central-%02d"%clampi(int(e.get("floor",1)),1,3)
			var name := str(e.get("source_name",current.name)).to_lower()
			for token: String in ["stair","entrance","threshold"]:
				if token in name: return StringName("safety:"+zone)
			return StringName(zone)
		if module.begins_with("M") and module.length()==3: return StringName("dorm-%02d"%int(module.trim_prefix("M")))
		current=current.get_parent()
	return &"room"


static func group_scale(group: StringName, lights_on: bool, quiet_mode: bool, occupied: PackedStringArray, usage_known: bool = false) -> float:
	if not lights_on: return 0.0
	# Evening is shared activity time; occupancy only selects quiet-hour rooms.
	if not quiet_mode: return 1.0
	var name := str(group)
	if name=="outdoor": return (0.25 if quiet_mode else 1.0) if lights_on else 0.0
	if name.begins_with("safety:"): return (0.18 if quiet_mode else 1.0) if lights_on else 0.0
	if name.begins_with("central-"):
		return 1.0 if name in occupied or (lights_on and not quiet_mode) else 0.0
	if name.begins_with("dorm-"):
		if usage_known: return 1.0 if name in occupied else 0.0
		return 1.0 if lights_on and not quiet_mode else 0.0
	return 1.0 if lights_on and not quiet_mode else 0.0


static func light_boost(light: Light3D, group: StringName, quiet_mode: bool = false) -> float:
	if bool(light.get_meta("estate_fixture_calibrated", false)): return 1.0
	if light.has_meta("estate_fixture_boost"): return float(light.get_meta("estate_fixture_boost"))
	return night_boost(group, quiet_mode)


static func night_boost(group: StringName, quiet_mode: bool = false) -> float:
	var name := str(group)
	return 12.5 if name.contains("central-") or (name.begins_with("dorm-") and not quiet_mode) else 1.0


static func emission_energy(material: BaseMaterial3D, source_energy: float, group: StringName, quiet_mode: bool = false) -> float:
	# Keep the accepted quiet-hour calibration. Evening only restores diffusers
	# that the importer actually reduced; other authored emission stays intact.
	if quiet_mode:
		return source_energy
	return float(material.get_meta(DAYLIGHT.NIGHT_EMISSION, source_energy))


static func occupied_zones(entities: Dictionary) -> PackedStringArray:
	var zones := PackedStringArray()
	for entity: Dictionary in entities.values():
		if not bool(entity.get("active",false)) or str(entity.get("posture","")) in ["sleeping","sleep","away"]: continue
		var zone := str(entity.get("zone_id",""))
		if (zone.begins_with("dorm-") or zone.begins_with("central-")) and zone not in zones: zones.append(zone)
	zones.sort()
	return zones


static func is_ordinary_light(light: Light3D, nest: Node) -> bool:
	return (
		light == nest.get_node_or_null("CeilingFill")
		or light.get_meta("asset_role", "") == "authored-daylight-fixture"
	)


static func is_ordinary_emission(material: BaseMaterial3D) -> bool:
	return (
		material.resource_name in ARRIVAL_EMISSION
		or DAYLIGHT._is_artificial(material.resource_name.to_lower())
		or DAYLIGHT._is_authored_bounce(material.resource_name.to_lower())
		or material.resource_name in FIXTURE_EMISSION
		or (material.get_meta("extras", {}) as Dictionary).has("color_temperature_kelvin")
	)
