extends RefCounted


static func matches_query(query: String) -> bool:
	var parameters := {}
	for part: String in query.trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2:
			parameters[pair[0]] = String(pair[1]).uri_decode()
	return parameters.get("mode") == "elfie_lab" and parameters.get("review") in ["chair", "sofa", "tour"]


static func is_requested() -> bool:
	if not OS.has_feature("web"):
		return false
	var query: Variant = JavaScriptBridge.eval("window.location.search")
	return query is String and matches_query(query)
