extends RefCounted

## Shared assertions for the current asset. These do not synthesize world data.
static func manifest_error(nest: ModularNest, manifest: Dictionary, capacity: int) -> String:
	var capabilities := manifest.get("capabilities", []) as Array
	for capability: String in ["semantic_anchors", "complete_actor_sync", "navigation"]:
		if capability not in capabilities:
			return "Missing declared capability: %s" % capability
	var zones := {}
	for descriptor: Dictionary in manifest.get("zones", []):
		var id := String(descriptor.get("zone_id", ""))
		if id.is_empty() or zones.has(id) or not bool(descriptor.get("active", false)):
			return "Invalid, duplicate or inactive physical zone: %s" % id
		zones[id] = true
	for room in range(1, 9):
		if not zones.has("dorm-%02d" % room):
			return "Capacity removed a real dormitory: %d" % room
	for level in range(1, 5):
		if not zones.has("central-%02d" % level):
			return "Missing real central floor: %d" % level
	if not zones.has("courtyard"):
		return "Missing complete courtyard zone"
	var descriptors := {}
	var active_beds := 0
	var physical_beds := 0
	var desk_chairs := 0
	for descriptor: Dictionary in manifest.get("anchors", []):
		var id := String(descriptor.get("anchor_id", ""))
		if id.is_empty() or id.begins_with("activity-") or descriptors.has(id):
			return "Invalid, retired or duplicate anchor: %s" % id
		descriptors[id] = descriptor
		if not zones.has(String(descriptor.get("zone_id", ""))):
			return "Anchor has no real zone: %s" % id
		var marker := nest.resolve_anchor(id)
		if not bool(descriptor.get("active", false)):
			if marker != null:
				return "Inactive anchor still resolves: %s" % id
		elif marker == null:
			return "Active anchor does not resolve: %s" % id
		else:
			if String(marker.get_meta("source_node", "")).is_empty():
				return "Anchor is not linked to an actual asset node: %s" % id
			if String(marker.get_meta("zone_id", "")) != String(descriptor["zone_id"]):
				return "Marker/manifest zone mismatch: %s" % id
			if String(descriptor["kind"]) in ["bed", "chair"]:
				var pose: Variant = marker.get_meta("interaction_transform", null)
				var expected := "sleeping" if descriptor["kind"] == "bed" else "sitting"
				if not pose is Transform3D or not (pose as Transform3D).is_finite():
					return "Furniture lacks a finite authored pose: %s" % id
				if marker.get_meta("interaction_posture", "") != expected:
					return "Furniture has an incorrect posture: %s" % id
	for room in range(1, 9):
		var zone := "dorm-%02d" % room
		if not descriptors.has(zone + "/door"):
			return "Missing real room door: %s" % zone
		for resident in range(1, 5):
			var bed_id := "%s/bed-%02d" % [zone, resident]
			var chair_id := "%s/chair-%02d" % [zone, resident]
			if not descriptors.has(bed_id) or not descriptors.has(chair_id):
				return "Missing physical bed/desk chair: %s resident %d" % [zone, resident]
			physical_beds += 1
			desk_chairs += 1
			var active := (room - 1) * 4 + resident <= capacity
			if bool(descriptors[bed_id]["active"]) != active:
				return "Capacity activation order mismatch: %s" % bed_id
			if active:
				active_beds += 1
	if physical_beds != 32 or desk_chairs != 32 or active_beds != capacity:
		return "Real room inventory or active bed count changed"
	for id: String in [
		"central-01/activity", "central-02/activity", "central-03/activity",
		"central-04/activity", "courtyard/activity", "courtyard/lakeside-seat",
		"courtyard/picnic-seat",
	]:
		if not descriptors.has(id) or nest.resolve_anchor(id) == null:
			return "Missing public anchor: %s" % id
	for room in range(1, 9):
		if nest.resolve_facility("dorm-%02d/rest" % room) == null:
			return "Missing real rest facility: %d" % room
	if (manifest.get("facilities", []) as Array).is_empty():
		return "Real facilities were not advertised"
	return ""


static func physical_error(nest: ModularNest) -> String:
	var physics := nest.get_node_or_null("Generated/EstatePhysics")
	if physics == null or physics.get_script() != load("res://rooms/estate/estate_physics.gd"):
		return "Complete estate physical owner is missing"
	if physics.find_children("*", "StaticBody3D", true, false).is_empty():
		return "Real architecture/furniture collision proxies are missing"
	return ""
