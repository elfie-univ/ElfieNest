extends RefCounted
## Offline guidance follows the existing paving and native sage stone inlays.
const GEOMETRY := preload("res://scripts/tools/outdoor_lighting_geometry.gd")
const PLAZA := "Flower preview | CY R003 reference seven-petal stone and ring-material connector"

static func build(source: Node3D, parent: Node3D, road: MeshInstance3D) -> bool:
	var plaza := source.find_child(PLAZA,true,false) as MeshInstance3D
	var reader := preload("res://rooms/estate/estate_outdoor_access.gd").new()
	var road_outline := _largest(reader._top_outlines(road,0))
	var plaza_outline := _largest(reader._top_outlines(plaza,0))
	# The connector is a separate material surface of the same paving mesh.
	for surface in range(1,plaza.mesh.get_surface_count()):
		var loops := reader._top_outlines(plaza,surface)
		for loop in loops:
			if GEOMETRY.area(loop)<0.1: continue
			var joined := Geometry2D.merge_polygons(plaza_outline,loop)
			if joined.size()==1: plaza_outline=joined[0]
	# The actual ring is open at the plaza. Union removes that internal join;
	# the remaining loops are the two real paving edges, including the fan apron.
	var outlines: Array[PackedVector2Array] = []
	# Millimetre-quantized imported triangle seams leave tiny numerical holes.
	# They are not paving boundaries or places to install a separate light loop.
	for outline: PackedVector2Array in Geometry2D.merge_polygons(road_outline,plaza_outline):
		if absf(GEOMETRY.area(outline))>0.01: outlines.append(outline)
	if outlines.size()!=2:
		push_error("Ring/plaza union must retain outer and inner paving edges")
		reader.free()
		return false
	var slabs := source.find_child("ROAD REF • ring large inset limestone slabs and edging",true,false) as MeshInstance3D
	var height := maxf((slabs.global_transform*slabs.get_aabb()).end.y,(plaza.global_transform*plaza.get_aabb()).end.y)+0.002
	var paths: Array[PackedVector3Array] = []
	for outline: PackedVector2Array in outlines:
		var points := _raised(outline,height)
		var strip := GEOMETRY.strip(parent,points,0.035,"RoadEdgeWarmRim_%02d"%paths.size())
		_finish(strip,0.8,Color(0.72,0.70,0.62),"road_edge")
		paths.append(points)
	parent.set_meta("road_edge_paths",paths)
	var pattern_paths: Array[PackedVector3Array] = []
	for surface in range(plaza.mesh.get_surface_count()):
		var original := plaza.get_active_material(surface) as BaseMaterial3D
		if original.resource_name!="Flower preview sage inlaid stone": continue
		for outline: PackedVector2Array in reader._top_outlines(plaza,surface):
			if absf(GEOMETRY.area(outline))<0.2: continue
			var points := _raised(outline,height+0.001)
			var strip := GEOMETRY.strip(parent,points,0.03,"PlazaFlowerOutline_%02d"%pattern_paths.size())
			var material := original.duplicate() as BaseMaterial3D
			material.resource_name="Outdoor concealed flower outline lamp"
			material.emission_enabled=true
			material.emission=Color(1.0,0.77,0.44)
			material.emission_energy_multiplier=0.4
			material.set_meta("concealed_guidance","flower_outline")
			strip.mesh.surface_set_material(0,material)
			strip.set_meta("guidance_source_surface",surface)
			pattern_paths.append(points)
	if pattern_paths.size()!=6:
		push_error("Native side-petal stone contours are missing: "+str(pattern_paths.size()))
		reader.free()
		return false
	# Six side petals are native stone inlays. The central petal and its stem
	# are painted on surface 0, so preserve that artwork and derive its fine edge mask.
	_artwork_glow(plaza,parent)
	parent.set_meta("plaza_pattern_paths",pattern_paths)
	parent.set_meta("guidance_source_plaza",PLAZA)
	reader.free()
	print("CONCEALED_GUIDANCE edges=",paths.size()," native_pattern_loops=",pattern_paths.size())
	return true

static func _artwork_glow(plaza: MeshInstance3D, parent: Node3D) -> void:
	var source := plaza.get_active_material(0) as BaseMaterial3D
	var image := source.albedo_texture.get_image()
	if image.is_compressed(): image.decompress()
	image.convert(Image.FORMAT_RGBA8)
	image.resize(1024,1024,Image.INTERPOLATE_LANCZOS)
	var pixels := image.get_data()
	var ink := PackedByteArray()
	ink.resize(1024*1024)
	for i in range(ink.size()): ink[i]=1 if pixels[i*4]<205 and pixels[i*4+1]<205 else 0
	var edges := PackedByteArray()
	edges.resize(ink.size())
	var lit := 0
	for y in range(1,1023):
		for x in range(1,1023):
			var i := y*1024+x
			if ink[i]!=0 and (ink[i-1]==0 or ink[i+1]==0 or ink[i-1024]==0 or ink[i+1024]==0):
				edges[i]=255
				lit+=1
	var mask := Image.create_from_data(1024,1024,false,Image.FORMAT_L8,edges)
	mask.generate_mipmaps()
	var material := source.duplicate() as BaseMaterial3D
	material.resource_name="Outdoor concealed flower artwork outline lamp"
	material.emission_enabled=true
	material.emission=Color(1.0,0.77,0.44)
	material.emission_energy_multiplier=0.4
	material.emission_texture=ImageTexture.create_from_image(mask)
	material.set_meta("concealed_guidance","flower_artwork")
	plaza.set_surface_override_material(0,material)
	parent.set_meta("plaza_artwork_edge_fraction",float(lit)/ink.size())

static func _largest(loops: Array[PackedVector2Array]) -> PackedVector2Array:
	var largest := PackedVector2Array()
	var size := 0.0
	for loop in loops:
		if absf(GEOMETRY.area(loop))>size:
			size=absf(GEOMETRY.area(loop))
			largest=loop
	assert(size>1.0,"Missing source paving footprint")
	return largest

static func _raised(loop: PackedVector2Array, height: float) -> PackedVector3Array:
	var points := PackedVector3Array()
	for point in loop: points.append(Vector3(point.x,height,point.y))
	points.append(points[0])
	return points

static func _finish(strip: MeshInstance3D, energy: float, color: Color, role: String) -> void:
	var material := strip.get_active_material(0) as BaseMaterial3D
	material.resource_name="Outdoor concealed road edge lamp"
	material.albedo_color=color
	material.emission_energy_multiplier=energy
	material.set_meta("concealed_guidance",role)
