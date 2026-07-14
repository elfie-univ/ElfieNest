@tool
extends SceneTree

## 家具提取脚本 - 完整版
## 从房间场景中提取家具，创建独立的预制件文件

const OUTPUT_BASE := "res://modular_rooms/assets/"

const ROOMS_TO_EXTRACT := [
	{
		"source": "res://room/common_area/1_kitchen_room.tscn",
		"category": "activity_equipment/kitchen",
		"extract_all_furniture": true,
		"exclude": ["Walls1", "Carpet"]
	},
	{
		"source": "res://room/common_area/2_sitting_room.tscn",
		"category": "activity_equipment/sitting",
		"extract_all_furniture": true,
		"exclude": ["Walls", "Carpet"]
	},
	{
		"source": "res://room/common_area/3_media_room.tscn",
		"category": "activity_equipment/media",
		"extract_all_furniture": true,
		"exclude": ["Walls", "Walls2"]
	},
	{
		"source": "res://room/common_area/4_gym.tscn",
		"category": "activity_equipment/gym",
		"extract_all_furniture": true,
		"exclude": ["Walls1", "Walls2"]
	},
	{
		"source": "res://room/common_area/5_garden.tscn",
		"category": "activity_equipment/garden",
		"extract_all_furniture": true,
		"exclude": []
	},
	{
		"source": "res://room/common_area/6_working_room.tscn",
		"category": "activity_equipment/working",
		"extract_all_furniture": true,
		"exclude": ["Walls2", "Walls3", "Flooring", "Curtains"]
	},
	{
		"source": "res://room/common_area/7_music_room.tscn",
		"category": "activity_equipment/music",
		"extract_all_furniture": true,
		"exclude": []
	},
	{
		"source": "res://room/common_area/8_bookroom.tscn",
		"category": "activity_equipment/bookroom",
		"extract_all_furniture": true,
		"exclude": ["Walls", "Flooring"]
	},
	{
		"source": "res://room/bedroom/bedroom.tscn",
		"category": "furniture/beds",
		"extract_all_furniture": true,
		"exclude": ["Walls", "Floor"]
	}
]


func _init():
	print("\n=== 家具提取工具 ===")
	print("从房间场景提取家具并创建独立预制件\n")
	
	var total_extracted := 0
	
	for room_info in ROOMS_TO_EXTRACT:
		var source_path: String = room_info["source"]
		var category: String = room_info["category"]
		var exclude_list: Array = room_info.get("exclude", [])
		
		print("📁 处理: %s" % source_path)
		
		if not ResourceLoader.exists(source_path):
			print("  ⚠️  文件不存在，跳过")
			continue
		
		var scene = load(source_path) as PackedScene
		if not scene:
			print("  ⚠️  无法加载场景")
			continue
		
		var instance = scene.instantiate() as Node3D
		var extracted_count := 0
		
		# 为这个房间创建输出目录
		var output_dir = OUTPUT_BASE + category + "/"
		
		# 提取所有家具节点
		for child in instance.get_children():
			var child_3d = child as Node3D
			if not child_3d:
				continue
			
			# 跳过排除列表中的节点
			if child_3d.name in exclude_list:
				continue
			
			# 提取这个家具
			var furniture_scene = _extract_furniture_node(child_3d)
			if furniture_scene:
				var output_path = output_dir + _sanitize_name(child_3d.name) + ".tscn"
				var save_result = ResourceSaver.save(furniture_scene, output_path)
				
				if save_result == OK:
					print("  ✅ 已提取: %s" % child_3d.name)
					extracted_count += 1
				else:
					print("  ❌ 保存失败: %s (错误码: %d)" % [child_3d.name, save_result])
		
		instance.queue_free()
		total_extracted += extracted_count
		print("  📊 本房间提取: %d 个家具\n" % extracted_count)
	
	print("=== 完成 ===")
	print("总共提取: %d 个家具预制件" % total_extracted)
	
	quit()


func _extract_furniture_node(source_node: Node3D) -> PackedScene:
	"""提取单个家具节点及其所有子节点"""
	var root := Node3D.new()
	root.name = source_node.name
	
	# 复制变换
	root.transform = source_node.transform
	
	# 递归复制子节点
	_copy_children_recursive(source_node, root)
	
	# 创建场景
	var scene := PackedScene.new()
	var result := scene.pack(root)
	
	if result != OK:
		root.queue_free()
		return null
	
	root.queue_free()
	return scene


func _copy_children_recursive(source: Node, target: Node):
	"""递归复制所有子节点"""
	for child in source.get_children():
		var duplicate = child.duplicate()
		target.add_child(duplicate)
		duplicate.owner = target
		
		# 如果有子节点，继续递归
		if child.get_child_count() > 0:
			_copy_children_recursive(child, duplicate)


func _sanitize_name(name: String) -> String:
	"""清理节点名称，使其适合作为文件名"""
	var result := name.to_lower()
	result = result.replace(" ", "_")
	result = result.replace("-", "_")
	
	# 移除特殊字符
	var valid_chars := "abcdefghijklmnopqrstuvwxyz0123456789_"
	var cleaned := ""
	for char in result:
		if char in valid_chars:
			cleaned += char
	
	return cleaned
