extends RefCounted
## Local review progress only. Playback completion is never visual acceptance.

const STAGES := [
	{"id": "arrival", "title": "01 / Rooftop adoption arrival"},
	{"id": "platform-exit", "title": "02 / Physically walk down platform steps"},
	{"id": "stairs", "title": "03 / Walk L4 > L3 > L2 > L1"},
	{"id": "doors", "title": "04 / Representative M01 sliding door (one room)"},
	{"id": "garden-door", "title": "05 / Paired garden door"},
	{"id": "locomotion", "title": "06 / Locomotion clip review"},
	{"id": "expressions", "title": "07 / Expressions and gestures"},
	{"id": "chair", "title": "08 / Desk swivel chair"},
	{"id": "sofa-central", "title": "09 / Central lounge sofa"},
	{"id": "sofa-cinema", "title": "10 / M01 cinema terrace sofa"},
	{"id": "sofa-tea", "title": "11 / M07 tea terrace sofa"},
	{"id": "sleep-back", "title": "12 / Bed approach, back sleep, duvet and exit"},
	{"id": "sleep-left", "title": "13 / Left-side sleep and duvet"},
	{"id": "sleep-right", "title": "14 / Right-side sleep and duvet"},
	{"id": "embodiment", "title": "15 / Bed embodiment cover"},
	{"id": "fountain", "title": "16 / Fountain jets, splash and ripples"},
	{"id": "spillway", "title": "17 / Spillway and lake inlet"},
	{"id": "lake", "title": "18 / Natural lake waves"},
	{"id": "water-night", "title": "19 / Night water colours and ring pulses"},
	{"id": "clip-inventory", "title": "20 / Remaining source clips (inventory comparison)"},
]

var index := -1
var running := false
var completed: Array[String] = []
var blocked: Dictionary = {}


static func auto_start(query: String) -> bool:
	var parameters := {}
	for part: String in query.trim_prefix("?").split("&"):
		var pair := part.split("=", true, 1)
		if pair.size() == 2: parameters[pair[0]] = String(pair[1]).uri_decode()
	return parameters.get("mode") == "animation_journey" and parameters.get("autoplay") == "1"


static func clip_sources() -> Dictionary:
	var runtime := preload("res://runtime/actor/actor_animation_runtime.gd")
	var result: Dictionary = runtime.SHARED_ANIMATIONS.duplicate()
	result.merge(runtime.PREVIEW_POSES)
	for name: String in ["Stand To Sit", "Sitting Idle", "Sit To Stand", "Step Onto Platform", "Jump Down", "Lying Down", "Laying Sleeping"]:
		result[name] = "res://characters/animation/candidates/%s.fbx" % name
	return result


func start() -> void:
	index = 0
	running = true
	completed.clear()
	blocked.clear()


func current() -> Dictionary:
	return STAGES[index] if index >= 0 and index < STAGES.size() else {}


func finish_current(success: bool, reason: String, position: Vector3) -> bool:
	if not running or current().is_empty():
		return false
	if not success:
		blocked = {"stage": current()["id"], "reason": reason, "position": [position.x, position.y, position.z]}
		running = false
		return false
	completed.append(current()["id"])
	index += 1
	running = index < STAGES.size()
	return true


func retry_current() -> bool:
	if blocked.is_empty() or current().is_empty():
		return false
	blocked.clear()
	running = true
	return true


func report() -> Dictionary:
	var pending: Array[String] = []
	for stage: Dictionary in STAGES:
		if not completed.has(stage["id"]): pending.append(stage["id"])
	return {"played": completed.duplicate(), "pending": pending, "blocked": blocked.duplicate(true), "accepted": false}
