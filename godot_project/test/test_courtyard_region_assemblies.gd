extends SceneTree
## Inspect saved geographic ownership against the canonical ground boundaries.
const BINDING:=preload("res://nest/assembly/glb_placement.gd")
const POSES:=preload("res://test/test_lotus_bay.gd")
const GROUND:="res://nest/courtyard/parts/ground/shared-ground.glb"
const AREAS:={"ground":"courtyard-ground","building":"building-greenery","forest":"forest-layout","waterside":"waterside-layout","meadow":"meadow-layout"}

func _initialize()->void:call_deferred("run")

static func transform_at(buffer:PackedFloat32Array,at:int)->Transform3D:
	return Transform3D(Basis(Vector3(buffer[at],buffer[at+4],buffer[at+8]),Vector3(buffer[at+1],buffer[at+5],buffer[at+9]),Vector3(buffer[at+2],buffer[at+6],buffer[at+10])),Vector3(buffer[at+3],buffer[at+7],buffer[at+11]))

static func verify(tree:SceneTree)->Dictionary:
	var file:=FileAccess.open(GROUND,FileAccess.READ)
	file.seek(12)
	var length:=file.get_32()
	file.get_32()
	var document:Dictionary=JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	file.close()
	var polygons:={}
	for key:String in document.extras.nest_ground_regions:
		var polygon:=PackedVector2Array()
		for p:Array in document.extras.nest_ground_regions[key][0]:polygon.append(Vector2(p[0],p[1]))
		polygons["ground" if key=="building" else key]=polygon
	var totals:={}
	var stone_count:=0
	var shrub_owners:={}
	var shore_shrub:={}
	var shore_shrub_owners:={}
	var ground_foliage_count:=0
	for area:String in AREAS:
		var scene:Node3D=(load("res://nest/courtyard/areas/%s/%s.scn"%[area,AREAS[area]]) as PackedScene).instantiate()
		tree.root.add_child(scene)
		var ground_count:=0
		var checked:=0
		for binding:Node in scene.find_children("*","Node3D",true,false):
			if binding.get_script()!=BINDING:continue
			for slot:int in binding.source_nodes.size():
				var node:GeometryInstance3D=binding.get_child(slot)
				var source:=str(binding.source_nodes[slot])
				var placement_path:=str(node.get_meta("v044_path",""))
				if binding.library.resource_path==GROUND and source in ["part_00000","terrain_forest","terrain_meadow","terrain_waterside"]:
					if str(node.get_meta("ground_region",""))!=area:
						scene.free()
						return {"error":"A region contains another region's land","area":area}
					ground_count+=1
					if area!="ground":
						var rectangle:=Rect2(polygons[area][0],Vector2.ZERO)
						for point:Vector2 in polygons[area]:rectangle=rectangle.expand(point)
						var box:AABB=node.mesh.get_aabb()
						if box.position.x<rectangle.position.x-.05 or box.end.x>rectangle.end.x+.05 or box.position.z<rectangle.position.y-.05 or box.end.z>rectangle.end.y+.05:
							scene.free()
							return {"error":"A geographic area contains a shared exterior shell","area":area,"bounds":str(box)}
				var library:String=binding.library.resource_path
				var plants:bool=library.ends_with("/plant-library.glb")
				var stone:bool=library.ends_with("/shore-stones.glb")
				var fixture:bool=library.ends_with("/outdoor-lights.glb")
				var shrub:bool=(library.ends_with("/forest-foliage.glb") and source in ["part_00006","part_00007","part_00008"]) or ((library.ends_with("/forest-wood.glb") or library.ends_with("/forest-twigs.glb")) and source=="part_00033")
				var ground_foliage:bool=library.ends_with("/forest-foliage.glb") and source=="part_00009"
				if not (plants or stone or fixture or shrub or ground_foliage):continue
				var mesh:Mesh=node.mesh if node is MeshInstance3D else node.multimesh.mesh
				var center:=mesh.get_aabb().get_center()
				var world:=POSES.pose_in(scene,node)
				var poses:Array[Transform3D]=[]
				if node is MultiMeshInstance3D:
					var data:Dictionary=binding.instance_batches[slot]
					var stride:=12+(4 if data.use_colors else 0)+(4 if data.use_custom_data else 0)
					for i:int in data.instance_count:poses.append(world*transform_at(data.buffer,i*stride))
				else:poses.append(world)
				for pose:Transform3D in poses:
					# These prototypes also form elevated tree crowns. Only the low
					# understorey clumps are assigned by their own root positions.
					if (shrub or ground_foliage) and pose.origin.y>1.0:continue
					# This eight-shoot shrub straddles the meadow/waterside seam.
					# Its shoots are components of one plant, not eight separate roots.
					if shrub and absf(pose.basis.y.length()-.483414173126221)<.000001 and Vector2(pose.origin.x,pose.origin.z).distance_to(Vector2(21.546094,36.681163))<1.0:
						var shoot:=var_to_bytes(pose).hex_encode().sha256_text()
						if not shore_shrub.has(shoot):shore_shrub[shoot]={}
						shore_shrub[shoot][library.get_file()+":"+source]=true
						shore_shrub_owners[area]=true
					if stone:stone_count+=1
					var point:Vector3=pose*center if absf(center.x)+absf(center.z)>3.0 else pose.origin
					if shrub and binding.has_meta("region_root"):point=binding.get_meta("region_root")
					var p:=Vector2(point.x,point.z)
					var expected:=""
					for key:String in ["ground","waterside","meadow","forest"]:
						if Geometry2D.is_point_in_polygon(p,polygons[key]):expected=key;break
					if expected.is_empty():
						var nearest:=INF
						for key:String in polygons:
							var polygon:PackedVector2Array=polygons[key]
							for i:int in polygon.size():
								var distance:=p.distance_to(Geometry2D.get_closest_point_to_segment(p,polygon[i],polygon[(i+1)%polygon.size()]))
								if distance<nearest:nearest=distance;expected=key
					if (plants or shrub or ground_foliage) and expected=="ground":expected="building"
					if plants and area=="ground":
						scene.free()
						return {"error":"Central greenery is still embedded in the ground assembly"}
					if expected!=area:
						var near:=INF
						var polygon:PackedVector2Array=polygons["ground" if area=="building" else area]
						for i:int in polygon.size():near=minf(near,p.distance_to(Geometry2D.get_closest_point_to_segment(p,polygon[i],polygon[(i+1)%polygon.size()])))
						if near>.0001:
							scene.free()
							return {"error":"A plant, shrub, stone or fixture belongs to another geographic region","area":area,"expected":expected,"position":str(p),"source":source,"library":library,"path":placement_path}
					if shrub:
						var key:=var_to_bytes(pose).hex_encode().sha256_text()
						if shrub_owners.has(key) and shrub_owners[key]!=area:
							scene.free()
							return {"error":"One shrub has stems and foliage in different regions"}
						shrub_owners[key]=area
					if ground_foliage:ground_foliage_count+=1
					checked+=1
		if ground_count!=(0 if area=="building" else 1):
			scene.free()
			return {"error":"Region must contain exactly its own land part","area":area,"land_parts":ground_count}
		totals[area]=checked
		scene.free()
	if stone_count!=149:return {"error":"A stone instance was lost or duplicated","stones":stone_count}
	if not shore_shrub.is_empty():
		return {"error":"The former shore shrub must be replaced with herbaceous plants"}
	return {"error":"","geographically_checked_instances":totals,"stone_instances":stone_count,"ground_parts":4,"low_shrub_roots":shrub_owners.size(),"ground_foliage_instances":ground_foliage_count}

func run()->void:
	var result:=verify(self)
	if not str(result.error).is_empty():push_error(JSON.stringify(result));quit(1);return
	print("COURTYARD_GEOGRAPHIC_ASSEMBLIES_OK ",JSON.stringify(result))
	quit(0)
