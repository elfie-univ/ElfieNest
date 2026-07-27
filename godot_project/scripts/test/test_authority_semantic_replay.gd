extends SceneTree

const RUNTIME_MODE := preload("res://runtime/runtime_mode.gd")
const AUTHORITY_SEMANTIC_EVENTS := preload(
	"res://runtime/authority_semantic_events.gd"
)


func _init() -> void:
	var web_events := _replay_authority("web_authority")
	var dedicated_events := _replay_authority("linux_dedicated")
	if web_events != dedicated_events:
		push_error("Web and Dedicated authority semantic events diverged")
		quit(1)
		return
	if web_events.size() != 3:
		push_error("Authority replay did not emit the expected event sequence")
		quit(1)
		return
	for event: Dictionary in web_events:
		if event.has("timestamp") or event.has("process_id"):
			push_error("Semantic replay leaked host-local fields")
			quit(1)
			return
	print("Authority semantic replay contract passed")
	quit()


func _replay_authority(host_name: String) -> Array[Dictionary]:
	var mode := RUNTIME_MODE.new()
	mode.setup("authority")
	if not mode.allows_authority_transport():
		return []
	var events := AUTHORITY_SEMANTIC_EVENTS.new()
	events.record("world_ready", {"ready": true, "host": host_name}, "")
	events.record(
		"intent_started",
		{"command_id": "move-42", "process_id": 9999},
		"move-42",
	)
	events.record(
		"intent_terminal",
		{
			"command_id": "move-42",
			"status": "completed",
			"occurred_at": "fixture-clock",
		},
		"move-42",
	)
	return events.events()
