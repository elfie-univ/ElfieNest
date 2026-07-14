extends SceneTree

func _init():
    build_cozy_bed()

func set_owner_recursive(node: Node, owner: Node):
    node.owner = owner
    for child in node.get_children():
        set_owner_recursive(child, owner)

func build_cozy_bed():
    var root = Node3D.new()
    root.name = "CozyBedCombo"
    
    # 1. Setup High Quality Environment
    var env_node = WorldEnvironment.new()
    var env = Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = Color(0.95, 0.9, 0.85) # Warm off-white
    
    # SSAO (Screen Space Ambient Occlusion) for contact shadows
    env.ssao_enabled = true
    env.ssao_radius = 0.5
    env.ssao_intensity = 2.0
    
    # Tonemap for indie game look
    env.tonemap_mode = Environment.TONE_MAPPER_ACES
    env.tonemap_exposure = 0.8 # Lower exposure to prevent blow out
    
    env_node.environment = env
    root.add_child(env_node)
    set_owner_recursive(env_node, root)
    
    # 2. Main Lighting (Sun / Window Light)
    var sun = DirectionalLight3D.new()
    sun.light_color = Color(1.0, 0.95, 0.8) # Warm sunlight
    sun.light_energy = 0.5 # Much softer sun
    sun.light_angular_distance = 5.0 # Very soft shadows
    sun.shadow_enabled = true
    sun.rotation_degrees = Vector3(-45, -30, 0)
    root.add_child(sun)
    set_owner_recursive(sun, root)
    
    # 3. Models
    var bed_res = load("res://assets/kenney_furniture/Models/GLTF format/bedSingle.glb")
    var desk_res = load("res://assets/kenney_furniture/Models/GLTF format/desk.glb")
    var chair_res = load("res://assets/kenney_furniture/Models/GLTF format/chairDesk.glb")
    var cabinet_res = load("res://assets/kenney_furniture/Models/GLTF format/bookcaseClosedDoors.glb")
    var laptop_res = load("res://assets/kenney_furniture/Models/GLTF format/laptop.glb")
    
    # BED (Origin is bottom corner. Extends X: 0 to 1.5, Z: 0 to -1.89)
    var bed = bed_res.instantiate()
    bed.position = Vector3(0, 1.4, 0) # Lowered the bed to 1.4m
    root.add_child(bed)
    set_owner_recursive(bed, root)
    
    # PILLARS for the bed
    var pillar_positions = [
        Vector3(0.05, 0.7, -0.05),
        Vector3(1.5, 0.7, -0.05),
        Vector3(0.05, 0.7, -1.8),
        Vector3(1.5, 0.7, -1.8)
    ]
    var mat_wood = StandardMaterial3D.new()
    mat_wood.albedo_color = Color(0.7, 0.5, 0.3) # Lighter wood
    for pos in pillar_positions:
        var post = CSGBox3D.new()
        post.size = Vector3(0.06, 1.4, 0.06) # Much thinner
        post.position = pos
        post.material = mat_wood
        root.add_child(post)
        set_owner_recursive(post, root)
    
    # LADDER (Placed on the right side: X=1.5, Z=-0.5)
    var ladder_root = Node3D.new()
    ladder_root.name = "Ladder"
    ladder_root.position = Vector3(1.5, 0, -0.5)
    ladder_root.rotation_degrees = Vector3(10, -90, 0) # Slanted slightly
    for i in range(4):
        var step = CSGBox3D.new()
        step.size = Vector3(0.3, 0.03, 0.06)
        step.position = Vector3(0, 0.3 + i*0.35, 0)
        step.material = mat_wood
        ladder_root.add_child(step)
    var rail1 = CSGBox3D.new()
    rail1.size = Vector3(0.04, 1.5, 0.06)
    rail1.position = Vector3(0.15, 0.75, 0)
    rail1.material = mat_wood
    ladder_root.add_child(rail1)
    var rail2 = CSGBox3D.new()
    rail2.size = Vector3(0.04, 1.5, 0.06)
    rail2.position = Vector3(-0.15, 0.75, 0)
    rail2.material = mat_wood
    ladder_root.add_child(rail2)
    root.add_child(ladder_root)
    set_owner_recursive(ladder_root, root)
    
    # DESK
    var desk = desk_res.instantiate()
    desk.position = Vector3(0.2, 0, -1.6)
    desk.scale = Vector3(1.2, 1.0, 1.2)
    root.add_child(desk)
    set_owner_recursive(desk, root)
    
    # LAPTOP
    var laptop = laptop_res.instantiate()
    laptop.position = Vector3(0.5, 0.76, -1.5) 
    laptop.rotation_degrees = Vector3(0, 15, 0)
    root.add_child(laptop)
    set_owner_recursive(laptop, root)
    
    # CHAIR
    var chair = chair_res.instantiate()
    chair.position = Vector3(0.5, 0, -1.0)
    chair.rotation_degrees = Vector3(0, 180, 0) 
    root.add_child(chair)
    set_owner_recursive(chair, root)
    
    # WARDROBE
    var cabinet = cabinet_res.instantiate()
    cabinet.position = Vector3(1.1, 0, -1.7)
    cabinet.scale = Vector3(1.0, 1.6, 1.0) 
    root.add_child(cabinet)
    set_owner_recursive(cabinet, root)
    
    # 4. Desk Lamp Light (OmniLight)
    var lamp_light = OmniLight3D.new()
    lamp_light.name = "DeskLampGlow"
    lamp_light.position = Vector3(0.8, 1.1, -1.6)
    lamp_light.light_color = Color(1.0, 0.8, 0.5) # Warm orange/yellow
    lamp_light.light_energy = 1.5
    lamp_light.shadow_enabled = true
    lamp_light.omni_range = 3.0
    root.add_child(lamp_light)
    set_owner_recursive(lamp_light, root)
    
    # Screen Light from laptop
    var screen_light = SpotLight3D.new()
    screen_light.position = Vector3(0.5, 1.0, -1.5)
    screen_light.rotation_degrees = Vector3(0, 0, 0) # Pointing towards the chair
    screen_light.light_color = Color(0.8, 0.9, 1.0) # Cool blue from screen
    screen_light.light_energy = 0.5
    screen_light.shadow_enabled = false
    screen_light.spot_range = 1.5
    screen_light.spot_angle = 60.0
    root.add_child(screen_light)
    set_owner_recursive(screen_light, root)
    
    var packed = PackedScene.new()
    packed.pack(root)
    ResourceSaver.save(packed, "res://assets/prefabs/cozy_bed_combo.tscn")
    
    # Instead of taking a screenshot which is hard headlessly in 1 frame,
    # we just generate the scene and exit.
    print("Cozy Bed Combo Generated!")
    
    # Note: Copying it to the user's 3d-model directory manually in bash.
    
    quit()
