extends RefCounted
## Explicit local fixtures, never a shortcut through a continuous journey.
const PLAN := preload("res://runtime/lab/estate_animation_journey_plan.gd")
const FUNCTIONS := [
	{"id":"arrival", "title":"顶楼领养到达"},
	{"id":"stairs", "title":"楼梯行走（一层代表）"},
	{"id":"doors", "title":"室内滑门（M01）"},
	{"id":"garden-door", "title":"花园双门"},
	{"id":"chair", "title":"书桌转椅"},
	{"id":"sofa", "title":"沙发坐卧"},
	{"id":"sleep", "title":"上床睡眠与起身"},
	{"id":"embodiment", "title":"床上具身化"},
	{"id":"water", "title":"水景"},
]
const VARIANTS := {
	"sofa":[{"id":"sofa-central", "title":"中央大厅沙发"}, {"id":"sofa-cinema", "title":"影院露台沙发"}, {"id":"sofa-tea", "title":"茶室露台沙发"}],
	"sleep":[{"id":"sleep-back", "title":"仰睡"}, {"id":"sleep-left", "title":"左侧睡"}, {"id":"sleep-right", "title":"右侧睡"}],
	"water":[{"id":"fountain", "title":"喷泉、水花与涟漪"}, {"id":"spillway", "title":"溢流与入湖"}, {"id":"lake", "title":"自然湖面波浪"}],
}
const CLIP_TITLES := {
	"idle":"待机", "walking":"走路", "running":"跑步", "jump":"跳跃", "twist_dance":"扭腰舞",
	"pose_waving":"挥手", "pose_thinking":"思考", "pose_victory":"胜利", "pose_thumbs_up":"点赞", "pose_hands_on_hips":"叉腰",
	"left_strafe":"向左侧移", "left_strafe_walking":"向左侧走", "left_turn":"左转", "left_turn_90":"左转九十度",
	"right_strafe":"向右侧移", "right_strafe_walking":"向右侧走", "right_turn":"右转", "right_turn_90":"右转九十度",
	"Stand To Sit":"站立到坐下", "Sitting Idle":"坐姿待机", "Sit To Stand":"坐下到站立", "Step Onto Platform":"踏上平台",
	"Jump Down":"跳下平台", "Lying Down":"躺下", "Laying Sleeping":"躺卧睡眠",
}

static func entries() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for index in range(FUNCTIONS.size()):
		result.append({"id":FUNCTIONS[index]["id"], "kind":"chapter", "title":"%02d / %s" % [index+1, FUNCTIONS[index]["title"]]})
	return result

static func source_entries() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for key: String in PLAN.clip_sources():
		result.append({"id":"clip:"+key, "kind":"clip", "clip":key, "title":str(CLIP_TITLES[key])})
	result.append({"id":"motion:nod_head", "kind":"gesture", "motion":"nod_head", "title":"点头"})
	result.append({"id":"motion:shake_head", "kind":"gesture", "motion":"shake_head", "title":"摇头"})
	return result

static func variants(id: String) -> Array:
	return VARIANTS.get(id, [])

static func resolve_entry(id: String, variant_index: int = 0, night: bool = false) -> Dictionary:
	for item: Dictionary in entries():
		if item["id"] != id: continue
		var result := item.duplicate()
		var options := variants(id)
		if not options.is_empty():
			if variant_index < 0 or variant_index >= options.size(): return {}
			result["id"] = options[variant_index]["id"]
			result["title"] = item["title"] + " / " + str(options[variant_index]["title"])
		if id == "water": result["night"] = night
		return result
	return {}

static func entry_for(id: String) -> Dictionary:
	for item: Dictionary in entries():
		if item["id"] == id: return resolve_entry(id)
		var options := variants(item["id"])
		for index in range(options.size()):
			if options[index]["id"] == id: return resolve_entry(item["id"], index)
	for item: Dictionary in source_entries():
		if item["id"] == id: return item.duplicate()
	return {}

static func uses_picker(query: String) -> bool:
	var parameters := {}
	for part: String in query.trim_prefix("?").split("&"):
		var pair := part.split("=",true,1)
		if pair.size()==2: parameters[pair[0]]=String(pair[1]).uri_decode()
	return parameters.get("mode")=="animation_journey" and parameters.get("playback","")!="continuous"

static func modules(id: String) -> Array[String]:
	if id in ["chair", "sleep-back", "sleep-left", "sleep-right", "embodiment"]: return ["M01"]
	if id.begins_with("sofa-"): return ["central", "M01", "M07"]
	if id in ["fountain", "spillway", "lake", "water-night"]: return []
	return ["central"]

static func needs_navigation(id: String) -> bool:
	return id == "stairs" or id == "chair" or id.begins_with("sofa-")
