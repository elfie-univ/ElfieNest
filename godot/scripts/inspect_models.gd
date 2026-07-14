extends SceneTree

func _init():
    inspect_models()
    quit()

func inspect_models():
    var models = [
        "res://assets/kenney_furniture/Models/GLTF format/bedSingle.glb",
        "res://assets/kenney_furniture/Models/GLTF format/desk.glb",
        "res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb",
        "res://assets/kenney_furniture/Models/GLTF format/bookcaseClosedDoors.glb",
        "res://assets/kenney_furniture/Models/GLTF format/laptop.glb"
    ]
    for path in models:
        var packed = load(path)
        var node = packed.instantiate()
        var aabb = _get_aabb_recursive(node)
        print("Model: ", path.get_file())
        print("  Size: ", aabb.size)
        print("  Position (Center): ", aabb.position + aabb.size/2)
        node.free()

func _get_aabb_recursive(node: Node) -> AABB:
    var aabb = AABB()
    var first = true
    var stack = [node]
    while stack.size() > 0:
        var curr = stack.pop_back()
        if curr is MeshInstance3D:
            var mesh_aabb = curr.get_aabb()
            var xform = curr.global_transform
            var transformed_aabb = xform * mesh_aabb
            if first:
                aabb = transformed_aabb
                first = false
            else:
                aabb = aabb.merge(transformed_aabb)
        for child in curr.get_children():
            stack.push_back(child)
    return aabb
