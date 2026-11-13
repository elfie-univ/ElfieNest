@tool
extends EditorScenePostImport
## Preserve the imported source rest for audition-local retargeting. No motion edits.


func _post_import(scene: Node) -> Object:
	var skeletons := scene.find_children("*", "Skeleton3D", true, false)
	if skeletons.size() != 1:
		push_error("Mixamo audition requires exactly one source skeleton")
		return scene
	var skeleton := skeletons[0] as Skeleton3D
	var frame := Transform3D.IDENTITY
	var ancestor: Node = skeleton
	while ancestor is Node3D:
		frame = (ancestor as Node3D).transform * frame
		ancestor = ancestor.get_parent()
	var bones := {}
	for bone in range(skeleton.get_bone_count()):
		var parent := skeleton.get_bone_parent(bone)
		bones[String(skeleton.get_bone_name(bone))] = {
			"rest": skeleton.get_bone_rest(bone),
			"parent_rest": skeleton.get_bone_global_rest(parent) if parent >= 0 else Transform3D.IDENTITY,
		}
	for player: AnimationPlayer in scene.find_children("*", "AnimationPlayer", true, false):
		for name: StringName in player.get_animation_library_list():
			player.get_animation_library(name).set_meta("mixamo_source_rest", {"bones": bones, "frame": frame})
	return scene
