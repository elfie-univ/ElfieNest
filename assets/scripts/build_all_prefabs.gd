extends SceneTree

func _init():
    build_leisure()
    build_dining()
    build_study()
    build_av()
    print("Successfully generated all public area prefabs!")
    quit()

func set_owner_recursive(node: Node, owner: Node):
    node.owner = owner
    for child in node.get_children():
        set_owner_recursive(child, owner)

func build_leisure():
    var root = Node3D.new()
    root.name = "LeisureTable"
    var table_res = load("res://assets/kenney_furniture/Models/GLTF format/tableRound.glb")
    var chair_res = load("res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb")
    
    var table = table_res.instantiate()
    root.add_child(table)
    set_owner_recursive(table, root)
    
    for i in range(4):
        var c = chair_res.instantiate()
        c.position = Vector3(cos(i*PI/2)*1.2, 0, sin(i*PI/2)*1.2)
        c.rotation_degrees = Vector3(0, -i*90 - 90, 0)
        root.add_child(c)
        set_owner_recursive(c, root)
        
    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://assets/prefabs/table_leisure.tscn")

func build_dining():
    var root = Node3D.new()
    root.name = "DiningTable"
    var table_res = load("res://assets/kenney_furniture/Models/GLTF format/table.glb")
    var chair_res = load("res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb")
    
    var table = table_res.instantiate()
    root.add_child(table)
    set_owner_recursive(table, root)
    
    for i in [-0.8, 0, 0.8]:
        var c1 = chair_res.instantiate()
        c1.position = Vector3(i, 0, 1.0)
        c1.rotation_degrees = Vector3(0, 180, 0)
        root.add_child(c1)
        set_owner_recursive(c1, root)
        
        var c2 = chair_res.instantiate()
        c2.position = Vector3(i, 0, -1.0)
        c2.rotation_degrees = Vector3(0, 0, 0)
        root.add_child(c2)
        set_owner_recursive(c2, root)
        
    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://assets/prefabs/table_dining.tscn")

func build_study():
    var root = Node3D.new()
    root.name = "StudyDesk"
    var desk_res = load("res://assets/kenney_furniture/Models/GLTF format/desk.glb")
    var chair_res = load("res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb")
    var laptop_res = load("res://assets/kenney_furniture/Models/GLTF format/laptop.glb")
    
    for i in [-0.8, 0.8]:
        var d = desk_res.instantiate()
        d.position = Vector3(i, 0, 0)
        root.add_child(d)
        set_owner_recursive(d, root)
        
        var l = laptop_res.instantiate()
        l.position = Vector3(i, 0.75, 0)
        root.add_child(l)
        set_owner_recursive(l, root)
        
        var c = chair_res.instantiate()
        c.position = Vector3(i, 0, 0.8)
        root.add_child(c)
        set_owner_recursive(c, root)
        
    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://assets/prefabs/study_desk.tscn")

func build_av():
    var root = Node3D.new()
    root.name = "AVRoom"
    var sofa_res = load("res://assets/kenney_furniture/Models/GLTF format/loungeSofa.glb")
    var tv_res = load("res://assets/kenney_furniture/Models/GLTF format/televisionModern.glb")
    var cabinet_res = load("res://assets/kenney_furniture/Models/GLTF format/cabinetTelevision.glb")
    
    var s = sofa_res.instantiate()
    s.position = Vector3(0, 0, 1.5)
    root.add_child(s)
    set_owner_recursive(s, root)
    
    var c = cabinet_res.instantiate()
    c.position = Vector3(0, 0, -1.5)
    c.rotation_degrees = Vector3(0, 180, 0)
    root.add_child(c)
    set_owner_recursive(c, root)
    
    var t = tv_res.instantiate()
    t.position = Vector3(0, 0.5, -1.5)
    t.rotation_degrees = Vector3(0, 180, 0)
    root.add_child(t)
    set_owner_recursive(t, root)
    
    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://assets/prefabs/av_room.tscn")
