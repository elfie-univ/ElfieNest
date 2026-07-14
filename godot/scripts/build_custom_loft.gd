extends SceneTree

func _init():
    var root = Node3D.new()
    root.name = "CustomLoftBed"
    
    var wood_mat = StandardMaterial3D.new()
    wood_mat.albedo_color = Color(0.85, 0.65, 0.45) # Warm wood color
    
    # 1. Top Bed
    var bed_res = load("res://assets/kenney_furniture/Models/GLTF format/bedSingle.glb")
    if bed_res:
        var bed = bed_res.instantiate()
        bed.position = Vector3(0.5, 1.4, 0)
        root.add_child(bed)
        
    # 2. Desk & Chair
    var desk_res = load("res://assets/kenney_furniture/Models/GLTF format/desk.glb")
    if desk_res:
        var desk = desk_res.instantiate()
        desk.position = Vector3(0.8, 0, 0.4)
        desk.rotation_degrees.y = 180
        root.add_child(desk)
        
    var chair_res = load("res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb")
    if chair_res:
        var chair = chair_res.instantiate()
        chair.position = Vector3(0.5, 0, 1.0)
        chair.rotation_degrees.y = 160
        root.add_child(chair)
        
    # 3. Wardrobe (Cabinet)
    var cab_res = load("res://assets/kenney_furniture/Models/GLTF format/bookcaseClosed.glb")
    if cab_res:
        var cab = cab_res.instantiate()
        cab.position = Vector3(-0.1, 0, 0)
        cab.rotation_degrees.y = 90
        root.add_child(cab)
        
    # 4. Stairs (Using CSG)
    var stairs_group = CSGCombiner3D.new()
    stairs_group.position = Vector3(-1.0, 0, 0)
    root.add_child(stairs_group)
    
    # Stairs steps
    for i in range(4):
        var step = CSGBox3D.new()
        step.size = Vector3(0.8, 0.4 * (i + 1), 0.8)
        step.position = Vector3(0, 0.2 * (i + 1), 1.2 - i * 0.4)
        step.material = wood_mat
        stairs_group.add_child(step)
        
    # Stairs side panel
    var side_panel = CSGBox3D.new()
    side_panel.size = Vector3(0.05, 2.0, 1.8)
    side_panel.position = Vector3(-0.4, 1.0, 0.5)
    side_panel.material = wood_mat
    stairs_group.add_child(side_panel)
    
    # Bed side rails (safety rails)
    var rail_front = CSGBox3D.new()
    rail_front.size = Vector3(1.6, 0.4, 0.05)
    rail_front.position = Vector3(0.5, 1.8, 0.9)
    rail_front.material = wood_mat
    root.add_child(rail_front)
    
    var rail_back = CSGBox3D.new()
    rail_back.size = Vector3(1.6, 0.4, 0.05)
    rail_back.position = Vector3(0.5, 1.8, -0.9)
    rail_back.material = wood_mat
    root.add_child(rail_back)
    
    # Support pillars
    for pos in [Vector3(-0.2, 0.7, -0.8), Vector3(1.2, 0.7, -0.8), Vector3(1.2, 0.7, 0.8), Vector3(-0.2, 0.7, 0.8)]:
        var pillar = CSGBox3D.new()
        pillar.size = Vector3(0.1, 1.4, 0.1)
        pillar.position = pos
        pillar.material = wood_mat
        root.add_child(pillar)

    # Set owner recursively so it actually saves to the PackedScene!
    _set_owner_recursive(root, root)

    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://assets/prefabs/custom_loft_bed.tscn")
    print("SUCCESS_BUILD")
    quit()

func _set_owner_recursive(node: Node, owner: Node):
    if node != owner:
        node.owner = owner
    for child in node.get_children():
        _set_owner_recursive(child, owner)
