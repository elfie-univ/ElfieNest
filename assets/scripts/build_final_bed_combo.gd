extends SceneTree

func _init():
    var root = Node3D.new()
    root.name = "FinalBedCombo"
    
    # 1. Base Frame (New Bed 3)
    var gltf = GLTFDocument.new()
    var state = GLTFState.new()
    # It's a .dae file, maybe GLTFDocument can't load it. Let's try direct load if the Godot project imported it.
    # Actually, we can't easily load imported .dae files by absolute path if they are in another project.
    # Wait, both projects share the same assets? No, I copied kenney_furniture into ElfieNest? No, ElfieNest has kenney_furniture?
    # Actually, the user wants to assemble it in THEIR Godot editor!
    quit()
