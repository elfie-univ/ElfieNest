extends SceneTree

func _init():
    var gltf = GLTFDocument.new()
    var state = GLTFState.new()
    var err = gltf.append_from_file("/Users/zhenli/3d-model/assets/custom_beds/pablo_animated/pablo_animated.glb", state)
    if err == OK:
        var animations = state.get_animations()
        print("--- ANIMATIONS ---")
        if animations.is_empty():
            print("No animations found.")
        else:
            for anim in animations:
                print("Animation name: ", anim.resource_name)
                print("Track count: ", anim.get_track_count())
                print("Length: ", anim.length, "s")
        print("------------------")
    else:
        print("Failed to load GLTF")
    quit()
