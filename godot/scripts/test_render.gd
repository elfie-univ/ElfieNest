extends SceneTree

func _init():
    # Delay to let engine initialize window and renderer
    call_deferred("take_shot")

func take_shot():
    var root = Node3D.new()
    
    # 1. Setup Environment
    var env_node = WorldEnvironment.new()
    var env = Environment.new()
    env.background_mode = Environment.BG_COLOR
    env.background_color = Color(0.8, 0.9, 1.0)
    env_node.environment = env
    root.add_child(env_node)
    
    var sun = DirectionalLight3D.new()
    sun.rotation_degrees = Vector3(-45, 45, 0)
    root.add_child(sun)
    
    # 2. Add bedBunk
    var bed_res = load("res://assets/kenney_furniture/Models/GLTF format/bedBunk.glb")
    var bed = bed_res.instantiate()
    root.add_child(bed)
    
    # 3. Add Camera
    var cam = Camera3D.new()
    cam.position = Vector3(2.5, 2.0, 3.0)
    cam.look_at(Vector3(0.5, 0.5, -0.5))
    root.add_child(cam)
    
    # Setup viewport
    var subviewport = SubViewport.new()
    subviewport.size = Vector2i(800, 600)
    subviewport.render_target_update_mode = SubViewport.UPDATE_ONCE
    subviewport.add_child(root)
    get_root().add_child(subviewport)
    
    # Wait for 2 frames to ensure render
    await create_timer(0.5).timeout
    
    var img = subviewport.get_texture().get_image()
    if img:
        img.save_png("res://test_render.png")
        print("SUCCESS_RENDER")
    else:
        print("FAILED_NO_IMAGE")
        
    quit()
