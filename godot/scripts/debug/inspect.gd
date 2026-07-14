extends SceneTree

func print_node(node: Node, indent: String = "", parent_transform: Transform3D = Transform3D()) -> void:
    var t = parent_transform
    var local_pos = Vector3()
    var local_scale = Vector3(1,1,1)
    
    if node is Node3D:
        t = t * node.transform
        local_pos = node.position
        local_scale = node.scale
    
    var info = indent + "- " + node.name + " (" + node.get_class() + ")"
    if node is Node3D:
        info += " | pos: " + str(local_pos) + " | g_pos: " + str(t.origin) + " | scale: " + str(local_scale)
    if node is CSGBox3D:
        info += " | size: " + str(node.size)
        
    print(info)
    
    for child in node.get_children():
        print_node(child, indent + "  ", t)

func _init():
    print("=== INSPECTING EXAMPLE_ROOM2 ===")
    var scene = load("res://room2/example_room2.tscn")
    if scene:
        var root = scene.instantiate()
        print_node(root)
    else:
        print("Failed to load scene")
        
    print("=== INSPECTING BEDROOM ===")
    var scene2 = load("res://room2/bedroom.tscn")
    if scene2:
        var root2 = scene2.instantiate()
        print_node(root2)
    else:
        print("Failed to load bedroom")
        
    print("=== INSPECTING ORIGINAL BEDROOM ===")
    var scene3 = load("res://room/bedroom/bedroom.tscn")
    if scene3:
        var root3 = scene3.instantiate()
        print_node(root3)
        
    print("ALL DONE")
    quit()
