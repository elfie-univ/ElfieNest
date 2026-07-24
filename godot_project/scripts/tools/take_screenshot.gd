extends SceneTree

func _init():
	var root = Node3D.new()
	var cam = Camera3D.new()
	cam.position = Vector3(0, 2, 5)
	root.add_child(cam)

	var mesh = CSGBox3D.new()
	root.add_child(mesh)

	var subviewport = SubViewport.new()
	subviewport.size = Vector2i(800, 600)
	subviewport.add_child(root)
	get_root().add_child(subviewport)

	await create_timer(1.0).timeout

	var img = subviewport.get_texture().get_image()
	img.save_png("test_screenshot.png")
	print("Screenshot saved!")
	quit()
