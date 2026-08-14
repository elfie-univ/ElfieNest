class_name NestSemanticSceneIndex
extends RefCounted

## Stable semantic IDs are indexed here; geometry remains in ModularNest.
static func sorted_anchor_ids(anchor_ids: Array[String]) -> Array[String]:
	var sorted_ids := anchor_ids.duplicate()
	sorted_ids.sort()
	return sorted_ids


static func active_anchor_ids(manifest: Dictionary) -> Array[String]:
	var result: Array[String] = []
	var raw_anchors: Variant = manifest.get("anchors", [])
	if not raw_anchors is Array:
		return result
	for raw_anchor: Variant in raw_anchors as Array:
		if not raw_anchor is Dictionary:
			continue
		var anchor := raw_anchor as Dictionary
		if bool(anchor.get("active", false)):
			var anchor_id := String(anchor.get("anchor_id", ""))
			result.append(anchor_id)
	return result


static func active_facility_ids(
	manifest: Dictionary,
	zone_id: String,
) -> Array[String]:
	var result: Array[String] = []
	var raw_facilities: Variant = manifest.get("facilities", [])
	if not raw_facilities is Array:
		return result
	for raw_facility: Variant in raw_facilities as Array:
		if not raw_facility is Dictionary:
			continue
		var facility := raw_facility as Dictionary
		if (
			bool(facility.get("active", false))
			and String(facility.get("zone_id", "")) == zone_id
		):
			var facility_id := String(facility.get("facility_id", ""))
			if not facility_id.is_empty():
				result.append("facility/%s" % facility_id)
	return result
