extends Node3D

@onready var nest: ModularNest = $Nest
@onready var characters: Node3D = $Characters


func add_character(
	character_scene: PackedScene, spawn_position: Vector3 = Vector3.ZERO
) -> CharacterBody3D:
	var instance := character_scene.instantiate()
	if not instance is CharacterBody3D:
		instance.queue_free()
		push_error("Character scene root must be CharacterBody3D")
		return null

	var character := instance as CharacterBody3D
	characters.add_child(character)
	character.position = spawn_position
	return character
