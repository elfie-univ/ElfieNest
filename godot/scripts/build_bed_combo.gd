extends SceneTree

func _init():
    var root = Node3D.new()
    root.name = "BedCombo"
    
    var desk_res = load("res://assets/kenney_furniture/Models/GLTF format/desk.glb")
    var chair_res = load("res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb")
    var bed_res = load("res://assets/kenney_furniture/Models/GLTF format/bedSingle.glb")
    var wardrobe_res = load("res://assets/kenney_furniture/Models/GLTF format/bookcaseClosedDoors.glb")
    var laptop_res = load("res://assets/kenney_furniture/Models/GLTF format/laptop.glb")
    
    # 1. Desk (bottom)
    var desk = desk_res.instantiate()
    desk.position = Vector3(0, 0, 0)
    root.add_child(desk)
    set_owner_recursive(desk, root)
    
    # 2. Chair
    var chair = chair_res.instantiate()
    chair.position = Vector3(0, 0, 0.6)
    root.add_child(chair)
    set_owner_recursive(chair, root)
    
    # 3. Laptop
    var laptop = laptop_res.instantiate()
    laptop.position = Vector3(0, 0.75, 0)
    root.add_child(laptop)
    set_owner_recursive(laptop, root)
    
    # 4. Wardrobe (side)
    var wardrobe = wardrobe_res.instantiate()
    wardrobe.position = Vector3(-1.3, 0, 0)
    root.add_child(wardrobe)
    set_owner_recursive(wardrobe, root)
    
    # 5. Bed (top)
    var bed = bed_res.instantiate()
    bed.position = Vector3(-0.6, 1.8, 0) # Elevate it above desk
    root.add_child(bed)
    set_owner_recursive(bed, root)
    
    # 6. Pillars (Support for bed)
    var mat_wood = StandardMaterial3D.new()
    mat_wood.albedo_color = Color(0.6, 0.4, 0.2) # Wood color
    
    for px in [-1.6, 0.4]:
        for pz in [-0.5, 0.5]:
            var leg = CSGCylinder3D.new()
            leg.radius = 0.05
            leg.height = 1.8
            leg.position = Vector3(px, 0.9, pz)
            leg.material = mat_wood
            leg.name = "Leg"
            root.add_child(leg)
            leg.owner = root
            
    # 7. Ladder
    var ladder = CSGBox3D.new()
    ladder.size = Vector3(0.1, 1.8, 0.4)
    ladder.position = Vector3(0.4, 0.9, 0)
    ladder.material = mat_wood
    ladder.name = "Ladder"
    root.add_child(ladder)
    ladder.owner = root

    # Save to disk
    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://assets/prefabs/bed_combo.tscn")
    print("Successfully generated res://assets/prefabs/bed_combo.tscn!")
    quit()

func set_owner_recursive(node: Node, owner: Node):
    node.owner = owner
    for child in node.get_children():
        set_owner_recursive(child, owner)
