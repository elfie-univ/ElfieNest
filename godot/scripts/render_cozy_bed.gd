extends SceneTree

func _init():
    call_deferred("take_shot")

func take_shot():
    # Load the scene we generated
    var packed = load("res://assets/prefabs/cozy_bed_combo.tscn")
    var scene = packed.instantiate()
    
    var subviewport = SubViewport.new()
    subviewport.size = Vector2i(1024, 768)
    subviewport.render_target_update_mode = SubViewport.UPDATE_ONCE
    
    subviewport.add_child(scene)
    
    # Add a camera looking at the scene
    var cam = Camera3D.new()
    cam.position = Vector3(1.5, 1.5, 2.0)
    # look_at must be called after adding to tree
    subviewport.add_child(cam)
    cam.look_at(Vector3(0.5, 0.7, -1.0))
    
    get_root().add_child(subviewport)
    
    await create_timer(1.0).timeout
    
    var img = subviewport.get_texture().get_image()
    if img:
        img.save_png("res://cozy_bed_combo_render.png")
        print("SUCCESS_RENDER")
    else:
        print("FAILED_NO_IMAGE")
        
    quit()
