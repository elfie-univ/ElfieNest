extends SceneTree

const ACTOR_CONTROLLER_SCRIPT := preload("res://runtime/actor_controller.gd")
const ACTOR_SCENES := {
	"dog": preload("res://characters/dog/dog.tscn"),
	"fox": preload("res://characters/fox/fox.tscn"),
	"cat": preload("res://characters/cat/cat.tscn"),
}


func _init() -> void:
	var main_scene := load("res://main.tscn") as PackedScene
	var main := main_scene.instantiate()
	root.add_child(main)
	await process_frame
	var nest := main.get_node("Nest") as ModularNest
	var characters := main.get_node("Characters") as Node3D
	var config := nest.apply_world_config({
		"nest_id": "actor-test",
		"bed_count": 4,
		"world_revision": 1,
	})
	if not bool(config.get("accepted", false)):
		push_error("Actor test world config was rejected")
		quit(1)
		return

	var controller := ACTOR_CONTROLLER_SCRIPT.new()
	root.add_child(controller)
	controller.setup(nest, characters, ACTOR_SCENES, true)
	var actors := [
		{
			"actor_id": "dog-1",
			"species": "dog",
			"home_anchor_id": "dorm-01/bed-02",
			"appearance": {},
		},
		{
			"actor_id": "fox-1",
			"species": "fox",
			"home_anchor_id": "dorm-01/bed-01",
			"appearance": {},
		},
		{
			"actor_id": "cat-1",
			"species": "cat",
			"home_anchor_id": "dorm-01/bed-03",
			"appearance": {},
		},
	]
	var first := controller.sync_actors(actors) as Dictionary
	var second := controller.sync_actors(actors) as Dictionary
	if not bool(first.get("accepted", false)) or first != second:
		push_error("Repeated complete actor sync was not idempotent")
		quit(1)
		return
	if characters.get_child_count() != 3:
		push_error("Complete actor sync did not create exactly three actors")
		quit(1)
		return
	if not _animation_tracks_resolve(controller.actor("fox-1")):
		push_error("Runtime animation tracks do not resolve to the actor skeleton")
		quit(1)
		return
	if not _animation_tracks_resolve(controller.actor("cat-1")):
		push_error("Procedural cat animation library could not be inspected")
		quit(1)
		return
	var reduced := controller.sync_actors([actors[1], actors[2]]) as Dictionary
	if not bool(reduced.get("accepted", false)):
		push_error("Actor catalog reduction was rejected")
		quit(1)
		return
	if characters.get_child_count() != 2 or controller.actor("dog-1") != null:
		push_error("Complete actor sync did not remove stale actor")
		quit(1)
		return
	var invalid := controller.sync_actors([
		{
			"actor_id": "bird-1",
			"species": "bird",
			"home_anchor_id": "dorm-01/bed-03",
			"appearance": {},
		},
	]) as Dictionary
	if bool(invalid.get("accepted", true)):
		push_error("Unsupported species was accepted")
		quit(1)
		return
	if characters.get_child_count() != 2:
		push_error("Rejected actor catalog partially changed the world")
		quit(1)
		return
	var invalid_home_anchor := controller.sync_actors([
		{
			"actor_id": "dog-2",
			"species": "dog",
			"home_anchor_id": "dorm-01/door",
			"appearance": {},
		},
	]) as Dictionary
	if bool(invalid_home_anchor.get("accepted", true)):
		push_error("Non-bed actor home anchor was accepted")
		quit(1)
		return
	if characters.get_child_count() != 2 or controller.actor("dog-2") != null:
		push_error("Rejected non-bed home anchor partially changed the world")
		quit(1)
		return

	print("Runtime actor catalog contract passed")
	quit()


func _animation_tracks_resolve(actor: ElfieActor) -> bool:
	var player := actor.get_node("AnimationPlayer") as AnimationPlayer
	var animation_root := player.get_node(player.root_node)
	for library_name in player.get_animation_library_list():
		var library := player.get_animation_library(library_name)
		for animation_name in library.get_animation_list():
			var animation := library.get_animation(animation_name)
			for index in range(animation.get_track_count()):
				var track_path := animation.track_get_path(index)
				var node_path := NodePath(track_path.get_concatenated_names())
				if animation_root.get_node_or_null(node_path) == null:
					return false
	return true
