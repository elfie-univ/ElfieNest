extends RefCounted
## Compile the same world into a display-free physical scene for hidden authority.
const PHYSICS := preload("res://rooms/estate/estate_physics.gd")
const SEMANTICS := preload("res://rooms/estate/estate_semantics.gd")
const ACCESS := preload("res://rooms/estate/estate_outdoor_access.gd")
const DOOR := preload("res://rooms/estate/estate_door.gd")

static func capture(world: Node3D, estate: Node3D, physics: Node3D) -> PackedScene:
 estate.name="CompleteEstate"
 physics.name="EstatePhysics"
 _stabilize_names(world)
 var semantics := SEMANTICS.new()
 semantics.build(world, estate)
 semantics.restrict_outdoor_anchors(physics.outdoor_access)
 var snapshot := _physical_copy(world) as Node3D
 snapshot.name = "Generated"
 var doors: Array[Dictionary] = []
 for entry: Dictionary in physics._doors:
  doors.append({"mesh":world.get_path_to(entry.mesh),"body":world.get_path_to(entry.body),"closed":entry.closed,"offset":entry.offset,"center":entry.center,"amount":0.0})
 snapshot.set_meta("authority_bindings", {"physics":world.get_path_to(physics),"collider_count":physics.collider_count,"doors":doors,"zones":semantics.zones,"centers":semantics._centers,"descriptors":semantics.descriptors,"facilities":semantics.facility_descriptors})
 _own(snapshot,snapshot)
 var packed := PackedScene.new()
 var error := packed.pack(snapshot)
 snapshot.free()
 assert(error==OK,"Physical authority scene could not be packed")
 return packed

static func _stabilize_names(node: Node) -> void:
 # Engine-generated @ names change when a PackedScene is instantiated.
 for child in node.get_children():
  if str(child.name).begins_with("@"):
   child.name="PhysicalNode_%d" % child.get_index()
  _stabilize_names(child)

static func _physical_copy(source: Node) -> Node:
 # Preserve every transform, collision shape, layer, mask and semantic marker.
 # Render meshes/materials/lights are not dependencies of this compiled scene.
 var target: Node3D
 if source is CollisionShape3D:
  var shape := CollisionShape3D.new()
  shape.shape=source.shape
  shape.disabled=source.disabled
  target=shape
 elif source is StaticBody3D:
  var body := StaticBody3D.new()
  body.collision_layer=source.collision_layer
  body.collision_mask=source.collision_mask
  body.physics_material_override=source.physics_material_override
  body.constant_linear_velocity=source.constant_linear_velocity
  body.constant_angular_velocity=source.constant_angular_velocity
  target=body
 elif source is Marker3D:
  target=Marker3D.new()
 else:
  target=Node3D.new()
 target.name=source.name
 if source is Node3D:
  target.transform=source.transform
  target.top_level=source.top_level
 for key in source.get_meta_list():
  var value: Variant=source.get_meta(key)
  if value is String or value is StringName or value is bool or value is int or value is Transform3D:
   target.set_meta(key,value)
 for group in source.get_groups(): target.add_to_group(group,true)
 # Its boundaries are restored from the same spatial resource, once.
 if source.name==&"OutdoorAccess":return target
 for child in source.get_children():
  if child is Light3D or child is Camera3D or child is NavigationRegion3D:continue
  target.add_child(_physical_copy(child))
 return target

static func _own(node: Node, owner_root: Node) -> void:
 for child in node.get_children():
  child.owner=owner_root
  _own(child,owner_root)

static func restore(generated: Node3D, data: Resource) -> Dictionary:
 var bindings: Dictionary=generated.get_meta("authority_bindings")
 var physics := generated.get_node(bindings.physics) as Node3D
 physics.set_script(PHYSICS)
 physics._spatial_data=data
 physics._complete_estate=true
 physics.loaded_precompiled=true
 physics.collider_count=int(bindings.collider_count)
 physics._static=physics.get_node("StaticGeometry")
 var access := physics.get_node("OutdoorAccess") as Node3D
 access.set_script(ACCESS)
 access.load_precompiled(data)
 physics.outdoor_access=access
 for stored: Dictionary in bindings.doors:
  var door: Dictionary=stored.duplicate()
  door.mesh=generated.get_node(stored.mesh)
  door.body=generated.get_node(stored.body)
  physics._doors.append(door)
  physics._door_controls.append(DOOR.new(door))
 var semantics := SEMANTICS.new()
 semantics.zones.assign(bindings.zones)
 semantics.descriptors.assign(bindings.descriptors)
 semantics.facility_descriptors.assign(bindings.facilities)
 semantics._centers=bindings.centers.duplicate()
 for marker: Marker3D in generated.find_children("*","Marker3D",true,false):
  if marker.has_meta("anchor_id"):semantics.anchors[str(marker.get_meta("anchor_id"))]=marker
  if marker.has_meta("facility_id"):semantics.facilities[str(marker.get_meta("facility_id"))]=marker
 return {"physics":physics,"semantics":semantics}
