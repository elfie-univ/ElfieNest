extends Node3D
## Review the accepted complete estate through its shared presentation code.

const REVIEW := preload("res://runtime/lab/estate_outdoor_lighting_review.gd")
var camera_owner: Node3D

static func is_requested() -> bool:
	if not OS.has_feature("web"):
		return false
	return str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('mode')")) == "path_lighting_review" and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('area')")) == "estate"

func _ready() -> void:
	var review := REVIEW.new()
	review.camera_owner = camera_owner
	add_child(review)
