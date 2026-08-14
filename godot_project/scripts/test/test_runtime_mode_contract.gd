extends SceneTree

const RUNTIME_MODE := preload("res://runtime/endpoint/runtime_mode.gd")


func _init() -> void:
	var mode := RUNTIME_MODE.new()
	mode.setup("authority")
	if not mode.allows_authority_transport() or not mode.disables_visual_runtime_services():
		push_error("Authority mode did not retain the authority-only contract")
		quit(1)
		return
	mode.setup("observer_room")
	if mode.allows_authority_transport() or mode.disables_visual_runtime_services():
		push_error("Room observer crossed the authority boundary")
		quit(1)
		return
	if not mode.requires_web_ready_signal():
		push_error("Room observer lost the Web readiness contract")
		quit(1)
		return
	mode.setup("observer_elfie")
	if mode.allows_authority_transport() or mode.disables_visual_runtime_services():
		push_error("Elfie observer crossed the authority boundary")
		quit(1)
		return
	if not mode.requires_web_ready_signal():
		push_error("Elfie observer lost the Web readiness contract")
		quit(1)
		return
	mode.setup("untrusted-mode")
	if mode.allows_authority_transport():
		push_error("Unknown mode failed open into authority")
		quit(1)
		return
	mode.setup("authority")
	if mode.allows_authority_transport(true):
		push_error("Nest Lab bypassed the authority startup guard")
		quit(1)
		return
	print("Runtime mode contract passed")
	quit()
