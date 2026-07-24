@tool
extends SceneTree

## 创建音乐室家具组合场景

const ACTIVITY_DEPTH := 3.7
const CELL_PITCH := 5.6
const WALL_HEIGHT := 3.0
const WALL_THICKNESS := 0.1
const OUTPUT_DIR := "res://rooms/common_area_layouts/generated"


func _init():
	print("\n创建: 音乐室 (music)")
	var mkdir_error := DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT_DIR))
	if mkdir_error != OK:
		push_error("无法创建布局输出目录: %s" % OUTPUT_DIR)
		quit(1)
		return
	
	# 创建根节点
	var root := Node3D.new()
	root.name = "music_furniture_set"
	
	# 添加标准参考墙（灰色半透明）
	var reference_walls := _create_reference_walls()
	reference_walls.name = "ReferenceWalls"
	root.add_child(reference_walls)
	reference_walls.owner = root
	
	# 添加家具容器节点（用户在这里拖拽家具）
	var furniture_container := Node3D.new()
	furniture_container.name = "Furniture"
	root.add_child(furniture_container)
	furniture_container.owner = root
	
	# 创建场景
	var scene := PackedScene.new()
	var result := scene.pack(root)
	
	if result == OK:
		var output_path := "%s/music_layout.tscn" % OUTPUT_DIR
		var save_result := ResourceSaver.save(scene, output_path)
		
		if save_result == OK:
			print("  ✅ 已保存: %s" % output_path)
		else:
			print("  ❌ 保存失败 (错误码: %d)" % save_result)
			root.queue_free()
			quit(1)
			return
	else:
		print("  ❌ 打包失败")
		root.queue_free()
		quit(1)
		return
	
	root.queue_free()
	
	print("\n=== 完成 ===")
	quit()


func _create_reference_walls() -> Node3D:
	"""创建标准参考墙（半透明，仅作位置参考）"""
	var walls_root := Node3D.new()
	
	# 后墙（走廊侧）
	var back_wall := _create_wall_node("BackWall",
		Vector3(WALL_THICKNESS, WALL_HEIGHT, CELL_PITCH),
		Vector3(-ACTIVITY_DEPTH / 2.0, WALL_HEIGHT / 2.0, 0.0),
		Color(0.5, 0.5, 0.5, 0.3)
	)
	walls_root.add_child(back_wall)
	back_wall.owner = walls_root
	
	# 外墙（活动区外侧）
	var outer_wall := _create_wall_node("OuterWall",
		Vector3(WALL_THICKNESS, WALL_HEIGHT, CELL_PITCH),
		Vector3(ACTIVITY_DEPTH / 2.0, WALL_HEIGHT / 2.0, 0.0),
		Color(0.5, 0.5, 0.5, 0.3)
	)
	walls_root.add_child(outer_wall)
	outer_wall.owner = walls_root
	
	# 左侧墙
	var left_wall := _create_wall_node("LeftWall",
		Vector3(ACTIVITY_DEPTH, WALL_HEIGHT, WALL_THICKNESS),
		Vector3(0.0, WALL_HEIGHT / 2.0, -CELL_PITCH / 2.0),
		Color(0.5, 0.5, 0.5, 0.3)
	)
	walls_root.add_child(left_wall)
	left_wall.owner = walls_root
	
	# 右侧墙
	var right_wall := _create_wall_node("RightWall",
		Vector3(ACTIVITY_DEPTH, WALL_HEIGHT, WALL_THICKNESS),
		Vector3(0.0, WALL_HEIGHT / 2.0, CELL_PITCH / 2.0),
		Color(0.5, 0.5, 0.5, 0.3)
	)
	walls_root.add_child(right_wall)
	right_wall.owner = walls_root
	
	# 地板参考
	var floor_mesh := _create_floor_node()
	walls_root.add_child(floor_mesh)
	floor_mesh.owner = walls_root
	
	return walls_root


func _create_wall_node(name: String, size: Vector3, position: Vector3, color: Color) -> MeshInstance3D:
	var wall := MeshInstance3D.new()
	wall.name = name
	wall.position = position
	
	var box := BoxMesh.new()
	box.size = size
	wall.mesh = box
	
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	wall.material_override = material
	
	return wall


func _create_floor_node() -> MeshInstance3D:
	var floor_node := MeshInstance3D.new()
	floor_node.name = "Floor"
	floor_node.position = Vector3(0.0, -0.01, 0.0)
	
	var box := BoxMesh.new()
	box.size = Vector3(ACTIVITY_DEPTH, 0.02, CELL_PITCH)
	floor_node.mesh = box
	
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.3, 0.3, 0.3, 0.2)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	floor_node.material_override = material
	
	return floor_node
