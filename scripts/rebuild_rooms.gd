extends SceneTree

func create_base_room_nodes(wall_color: Color, floor_color: Color) -> Array:
    var nodes = []
    var room_w = 6.0
    var room_d = 5.0
    var wall_th = 0.1
    var h = 3.5
    
    var wall_mat = StandardMaterial3D.new()
    wall_mat.albedo_color = wall_color
    
    var floor_mat = StandardMaterial3D.new()
    floor_mat.albedo_color = floor_color
    
    var floor_node = CSGBox3D.new()
    floor_node.name = "Floor"
    floor_node.size = Vector3(room_w + wall_th*2, 0.1, room_d + wall_th)
    floor_node.position = Vector3(0, -0.05, -room_d/2.0 - wall_th/2.0)
    floor_node.material = floor_mat
    nodes.append(floor_node)
    
    var back_wall = CSGBox3D.new()
    back_wall.name = "BackWall"
    back_wall.size = Vector3(room_w + wall_th*2, h, wall_th)
    back_wall.position = Vector3(0, h/2.0, -room_d - wall_th/2.0)
    back_wall.material = wall_mat
    nodes.append(back_wall)
    
    var left_wall = CSGBox3D.new()
    left_wall.name = "LeftWall"
    left_wall.size = Vector3(wall_th, h, room_d)
    left_wall.position = Vector3(-room_w/2.0 - wall_th/2.0, h/2.0, -room_d/2.0)
    left_wall.material = wall_mat
    nodes.append(left_wall)
    
    var right_wall = CSGBox3D.new()
    right_wall.name = "RightWall"
    right_wall.size = Vector3(wall_th, h, room_d)
    right_wall.position = Vector3(room_w/2.0 + wall_th/2.0, h/2.0, -room_d/2.0)
    right_wall.material = wall_mat
    nodes.append(right_wall)
    
    return nodes

func fix_owner(node: Node, root: Node):
    if node != root and node.owner != root:
        node.owner = root
    if node != root and node.scene_file_path != "":
        return 
        
    for child in node.get_children():
        fix_owner(child, root)

func build_new_bedroom():
    var old_scene = load("res://room/bedroom/bedroom.tscn")
    var old_root = old_scene.instantiate()
    
    var new_root = Node3D.new()
    new_root.name = "Bedroom"
    
    var wall_color = Color(0.9, 0.9, 0.95) # Made it brighter, off-white
    var floor_color = Color(0.85, 0.85, 0.85)
    var base_nodes = create_base_room_nodes(wall_color, floor_color)
    
    for n in base_nodes:
        new_root.add_child(n)

    var f_node = Node3D.new()
    f_node.name = "FurnitureContainer"
    new_root.add_child(f_node)
    
    var carpet = old_root.get_node_or_null("convert_node/bedroom/floor/Carpet")
    if carpet:
        carpet.get_parent().remove_child(carpet)
        f_node.add_child(carpet)
        carpet.scale = Vector3(0.2, 0.2, 0.2)
        # Fix: do NOT rotate the carpet, it was already flat!
        carpet.position = Vector3(0, 0.01, -2.5)
        
    var beds = old_root.get_node_or_null("convert_node/beds")
    if beds:
        beds.get_parent().remove_child(beds)
        f_node.add_child(beds)
        # Fix: apply the 0.2 scale that the beds lost from their original parent!
        beds.scale = Vector3(0.2, 0.2, 0.2)
        beds.position = Vector3(0, 0, -2.5) 
        
    var pic = old_root.get_node_or_null("convert_node/bedroom/Picture14")
    if pic:
        pic.get_parent().remove_child(pic)
        f_node.add_child(pic)
        pic.scale = Vector3(0.2, 0.2, 0.2)
        # Fix: Center the internal mesh so it doesn't fly outside the room
        if pic.get_child_count() > 0:
            pic.get_child(0).position = Vector3(0, 0, 0)
        pic.position = Vector3(0, 2.0, -4.8) 
        
    fix_owner(new_root, new_root)

    var packed = PackedScene.new()
    packed.pack(new_root)
    ResourceSaver.save(packed, "res://room2/bedroom.tscn")
    old_root.free()

func build_new_kitchen():
    var old_scene = load("res://room/common_area/1_kitchen_room.tscn")
    var old_root = old_scene.instantiate()
    
    var new_root = Node3D.new()
    new_root.name = "KitchenRoom"
    
    var wall_color = Color(1.0, 0.95, 0.8) # Adjusted yellow
    var floor_color = Color(0.95, 0.9, 0.8)
    var base_nodes = create_base_room_nodes(wall_color, floor_color)
    
    for n in base_nodes:
        new_root.add_child(n)

    var f_node = Node3D.new()
    f_node.name = "FurnitureContainer"
    new_root.add_child(f_node)
    
    f_node.scale = Vector3(0.01, 0.01, 0.01)
    f_node.position = Vector3(-1.0, 0, -1.0) 
    
    var children_to_move = []
    for child in old_root.get_children():
        if "wall" in child.name.to_lower() or "floor" in child.name.to_lower():
            continue
        children_to_move.append(child)
        
    for child in children_to_move:
        child.get_parent().remove_child(child)
        f_node.add_child(child)
        
    fix_owner(new_root, new_root)
        
    var packed = PackedScene.new()
    packed.pack(new_root)
    ResourceSaver.save(packed, "res://room2/1_kitchen_room.tscn")
    old_root.free()

func build_example_room():
    var root = Node3D.new()
    root.name = "ExampleRoom2"
    
    var floor_node = CSGBox3D.new()
    floor_node.name = "CorridorFloor"
    floor_node.size = Vector3(4.0, 0.1, 10.0)
    floor_node.position = Vector3(0, -0.05, -5.0)
    var floor_mat = StandardMaterial3D.new()
    floor_mat.albedo_color = Color(0.6, 0.6, 0.6)
    floor_node.material = floor_mat
    root.add_child(floor_node)
    
    var b_scene = load("res://room2/bedroom.tscn")
    if b_scene:
        var bedroom = b_scene.instantiate()
        bedroom.position = Vector3(2.0, 0, -2.5) 
        bedroom.rotation_degrees = Vector3(0, -90, 0)
        root.add_child(bedroom)
        
    var k_scene = load("res://room2/1_kitchen_room.tscn")
    if k_scene:
        var kitchen = k_scene.instantiate()
        kitchen.position = Vector3(-2.0, 0, -2.5)
        kitchen.rotation_degrees = Vector3(0, 90, 0)
        root.add_child(kitchen)
        
    fix_owner(root, root)
        
    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://room2/example_room2.tscn")

func _init():
    build_new_bedroom()
    build_new_kitchen()
    build_example_room()
    print("ALL DONE")
    quit()
