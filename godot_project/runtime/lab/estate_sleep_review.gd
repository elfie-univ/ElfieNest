extends Node3D
## One authored duvet and local, reversible sleep presentation; no world state.
const ARM_POSE := preload("res://runtime/lab/estate_sleep_arm_pose.gd")
const DUVET := preload("res://runtime/lab/estate_authored_duvet.gd")
const CYCLE := 20.0
var mode := "side-left"
var arm_pose: Dictionary = {}
var blanket: MeshInstance3D
var source_duvet_mesh: Mesh
var head_position := Vector3.ZERO
var animation_stage := "covered"
var _saved_bone_rotations: Dictionary = {}
var _body: ElfieActor
var _visual: Node3D
var _base := Transform3D.IDENTITY
var _hips: Skeleton3D
var _axis := Vector3.FORWARD
var _across := Vector3.RIGHT
var _contact := Vector3.ZERO
var _owner: Node3D
var _duvet: RefCounted
var _neutral: Array[Dictionary] = []
var _poses: Dictionary = {}
var _standing: Dictionary
var _seated: Dictionary
var _elapsed := 7.0
var _active := ""
var _last_stage := ""
var _walk_direction := Vector3.ZERO
var _bedside_sign := -1.0
var grip_report: Dictionary = {}

func bind(body: ElfieActor, duvet: MeshInstance3D, owner: Node3D) -> void:
	_body = body
	_owner = owner
	_visual = body.get_node("VisualRoot")
	body.get("_animation_runtime").advance(1.0)
	# This explicit local preview owns its visual clock only.
	body.set_process(false)
	_base = _visual.global_transform
	for skeleton: Skeleton3D in body.find_children("*", "Skeleton3D", true, false):
		if skeleton.find_bone("mixamorig:Hips") >= 0 or skeleton.find_bone("mixamorig_Hips") >= 0:
			_hips = skeleton
	for index in range(_hips.get_bone_count()):
		_saved_bone_rotations[index] = _hips.get_bone_pose_rotation(index)
		_neutral.append({"rotation": _hips.get_bone_pose_rotation(index), "position": _hips.get_bone_pose_position(index)})
	_contact = _bone("Hips")
	head_position = _bone("Head")
	_axis = (_base.basis.y * Vector3(1,0,1)).normalized()
	_across = _axis.cross(Vector3.UP).normalized()
	blanket = duvet
	_duvet = DUVET.new()
	_duvet.bind(duvet)
	source_duvet_mesh = _duvet.original
	_make_upright_poses()
	set_mode(mode)

func _bone(suffix: String) -> Vector3:
	return DUVET._bone(_hips, suffix)


func bind_actor(body: ElfieActor) -> String:
	# Transfer only this pose/duvet controller between identical local rigs.
	# The journey separately requires physical arrival and furniture contact.
	var skeleton := body._furniture_hips().get("skeleton") as Skeleton3D
	if skeleton == null or skeleton.get_bone_count() != _hips.get_bone_count():
		return "sleep_rig_mismatch"
	for index in range(_hips.get_bone_count()):
		if skeleton.get_bone_name(index) != _hips.get_bone_name(index): return "sleep_rig_mismatch"
	if body.species_id != _body.species_id: return "sleep_species_mismatch"
	_body = body
	_visual = body.get_node("VisualRoot")
	_hips = skeleton
	return ""

func _restore_neutral() -> void:
	for index in range(_neutral.size()):
		_hips.set_bone_pose_rotation(index, _neutral[index]["rotation"])
		_hips.set_bone_pose_position(index, _neutral[index]["position"])

func _snapshot() -> Dictionary:
	var bones: Array[Dictionary] = []
	for index in range(_hips.get_bone_count()):
		bones.append({"rotation": _hips.get_bone_pose_rotation(index), "position": _hips.get_bone_pose_position(index)})
	return {"visual": _visual.global_transform, "bones": bones}

func _apply_snapshot(pose: Dictionary) -> void:
	_visual.global_transform = pose["visual"]
	for index in range(_hips.get_bone_count()):
		_hips.set_bone_pose_rotation(index, pose["bones"][index]["rotation"])
		_hips.set_bone_pose_position(index, pose["bones"][index]["position"])

func _blend(a: Dictionary, b: Dictionary, amount: float) -> void:
	_visual.global_transform = (a["visual"] as Transform3D).interpolate_with(b["visual"], amount)
	for index in range(_hips.get_bone_count()):
		var left: Dictionary = a["bones"][index]
		var right: Dictionary = b["bones"][index]
		_hips.set_bone_pose_rotation(index, (left["rotation"] as Quaternion).slerp(right["rotation"], amount))
		_hips.set_bone_pose_position(index, (left["position"] as Vector3).lerp(right["position"], amount))

func _make_upright_poses() -> void:
	_restore_neutral()
	var center_x := source_duvet_mesh.get_aabb().get_center().x
	for mesh: MeshInstance3D in blanket.get_parent().find_children("*", "MeshInstance3D", true, false):
		var extras := mesh.get_meta("extras", {}) as Dictionary
		if extras.get("module") == "M01" and str(extras.get("source_name", "")).contains("continuous lower floor"):
			var center := blanket.to_local(mesh.global_transform*mesh.get_aabb().get_center())
			_bedside_sign = signf(center.x-center_x)
	_walk_direction = blanket.global_basis.x.normalized()*_bedside_sign
	var basis := Basis.looking_at(-_walk_direction, Vector3.UP).scaled(_base.basis.get_scale())
	_visual.global_transform = Transform3D(basis, Vector3.ZERO)
	var beside := blanket.to_global(Vector3(center_x+_bedside_sign*0.86, 0, 0.12))
	var hips := _bone("Hips")
	_visual.global_position += Vector3(beside.x-hips.x, 0, beside.z-hips.z)
	var floor_y := blanket.to_global(Vector3.ZERO).y
	var min_y := INF
	for point: Vector3 in DUVET.skin_points(_body, _hips): min_y = minf(min_y, point.y)
	_visual.global_position.y += floor_y + 0.005 - min_y
	_standing = _snapshot()
	for suffix: String in ["LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"]:
		var index := ARM_POSE._bone(_hips, suffix)
		var angle := -PI/2.0 if suffix.ends_with("UpLeg") else PI/2.0
		_hips.set_bone_pose_rotation(index, _hips.get_bone_pose_rotation(index)*Quaternion(Vector3.RIGHT,angle))
	_visual.global_position += blanket.to_global(Vector3(center_x+_bedside_sign*0.40, 0.59, 0.12)) - _bone("Hips")
	_seated = _snapshot()

func set_mode(value: String) -> void:
	mode = value
	if not _poses.has(value):
		_restore_neutral()
		var angle := 0.0 if value == "back" else deg_to_rad(72.0)*(1.0 if value == "side-left" else -1.0)
		var rotation := Basis(_axis, angle)
		var pose := _base
		pose.basis = rotation * pose.basis
		pose.origin = _contact + rotation * (pose.origin-_contact)
		_visual.global_transform = pose
		_settle_feet()
		_settle_tail()
		arm_pose = ARM_POSE.apply_back(_hips, _visual)
		_poses[value] = _snapshot()
	else:
		_apply_snapshot(_poses[value])
	var runtime: RefCounted = _body.get("_animation_runtime")
	runtime.transition_from(runtime.capture_visual_pose(), "sleeping")
	runtime.advance(1.0)
	_duvet.build_pose(_body, _hips)
	_elapsed = 7.0
	sample_bedding(_elapsed)

func _settle_feet() -> void:
	# Lower the real ankles into a relaxed, extended pose before fitting cloth.
	# The duvet must not invent a big padded mound over upright toes.
	for prefix: String in ["Left", "Right"]:
		var upper := ARM_POSE._bone(_hips,prefix+"UpLeg")
		var lower := ARM_POSE._bone(_hips,prefix+"Leg")
		var foot := ARM_POSE._bone(_hips,prefix+"Foot")
		var target := blanket.to_local(_bone(prefix+"Foot"))
		target.x = source_duvet_mesh.get_aabb().get_center().x+(0.10 if prefix=="Right" else -0.10)
		target.y = source_duvet_mesh.get_aabb().end.y+0.085
		target.z += 0.08
		ARM_POSE._solve(_hips,upper,lower,foot,blanket.to_global(target),Vector3.UP-_axis*0.2)
		var toe := ARM_POSE._bone(_hips,prefix+"ToeBase")
		if toe >= 0:
			ARM_POSE._swing(_hips,foot,ARM_POSE._point(_hips,toe)-ARM_POSE._point(_hips,foot),-_axis)

func _settle_tail() -> void:
	var tail := ARM_POSE._bone(_hips,"Tail_Bone")
	if tail<0: return
	var points := DUVET.skin_points(_body,_hips)
	var offset := 0
	var center := Vector3.ZERO
	var count := 0
	for mesh: MeshInstance3D in _body.find_children("*","MeshInstance3D",true,false):
		if mesh.skin==null or mesh.mesh==null: continue
		for surface in range(mesh.mesh.get_surface_count()):
			var arrays := mesh.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			var stride := bones.size()/vertices.size()
			for i in range(vertices.size()):
				for j in range(stride):
					if str(mesh.skin.get_bind_name(bones[i*stride+j])).ends_with("Tail_Bone") and weights[i*stride+j]>0.65:
						center+=points[offset+i]
						count+=1
			offset+=vertices.size()
	if count>0:
		ARM_POSE._swing(_hips,tail,center/float(count)-ARM_POSE._point(_hips,tail),-_axis-Vector3.UP*0.15)

func sample_bedding(seconds: float) -> void:
	var t := fposmod(seconds,CYCLE)
	var sleeping: Dictionary = _poses[mode]
	var cover := 0.0
	var opened := 0.0
	var lift := 0.0
	if t < 1.5:
		animation_stage = "approach"
		_walk(1.0-smoothstep(0.0,1.5,t), t)
		# Face the actual direction of approach, then turn at the bed edge.
		_visual.global_basis = _visual.global_basis.rotated(Vector3.UP,PI*(1.0-smoothstep(0.9,1.5,t)))
		opened = 0.0
	elif t < 2.3:
		animation_stage = "sit_on_bed_edge"
		_blend(_standing,_seated,smoothstep(1.5,2.3,t))
		opened = smoothstep(1.9,2.3,t)
	elif t < 3.3:
		animation_stage = "lie_down"
		_blend(_seated,sleeping,smoothstep(2.3,3.3,t))
		opened = 1.0
	elif t < 5.5:
		animation_stage = "pull_original_duvet"
		_apply_snapshot(sleeping)
		cover = smoothstep(3.7,5.5,t)
		opened = 1.0
		lift = sin(cover*PI)*0.085
	elif t < 12.0:
		animation_stage = "covered_breathing"
		_apply_snapshot(sleeping)
		cover = 1.0
	elif t < 14.0:
		animation_stage = "fold_duvet_down"
		_apply_snapshot(sleeping)
		cover = 1.0-smoothstep(12.4,14.0,t)
		opened = 1.0
		lift = sin(cover*PI)*0.07
	elif t < 15.0:
		animation_stage = "sit_up"
		_blend(sleeping,_seated,smoothstep(14.0,15.0,t))
		opened = 1.0-smoothstep(14.4,15.0,t)
	elif t < 16.0:
		animation_stage = "stand_up"
		_blend(_seated,_standing,smoothstep(15.0,16.0,t))
		opened = 0.0
	else:
		animation_stage = "leave_and_lay_back"
		_walk(smoothstep(16.0,18.0,t), t-16.0)
		opened = 0.0
	var breath := sin((t-5.5)*TAU/4.2)*0.004 if t >=5.5 and t<12.0 else 0.0
	if t>=5.5 and t<12.0:
		var spine := ARM_POSE._bone(_hips,"Spine2")
		_hips.set_bone_pose_rotation(spine,_hips.get_bone_pose_rotation(spine)*Quaternion(Vector3.RIGHT,breath*2.0))
	var body_weight := smoothstep(2.3,3.3,t)*(1.0-smoothstep(14.0,16.0,t))
	_duvet.sample(cover,opened,lift,breath,body_weight)
	grip_report = {}
	var grip := 0.0
	if t>=1.5 and t<2.7: grip = smoothstep(1.5,1.9,t)*(1.0-smoothstep(2.3,2.7,t))
	if t>=3.3 and t<5.9: grip = smoothstep(3.3,3.7,t)*(1.0-smoothstep(5.5,5.9,t))
	if t>=12.0 and t<15.3: grip = smoothstep(12.0,12.4,t)*(1.0-smoothstep(15.0,15.3,t))
	_reach_duvet(grip)

func _walk(distance: float, seconds: float) -> void:
	_apply_snapshot(_standing)
	var player: AnimationPlayer = _body.get("_animation_player")
	if player.has_animation("walking"):
		player.play("walking")
		player.seek(fposmod(seconds,player.get_animation("walking").length),true)
		player.pause()
	_visual.global_position += _walk_direction * distance * 0.9

func _reach_duvet(weight: float) -> void:
	if weight <= 0.0: return
	var points: PackedVector3Array = blanket.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var rest: PackedVector3Array = source_duvet_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var bounds := source_duvet_mesh.get_aabb()
	# Use the upper/free arm on side poses, keeping the lower arm out of the bed.
	var prefix := "Left" if _bone("LeftArm").y>=_bone("RightArm").y else "Right"
	var sign_value := 1.0 if prefix=="Left" else -1.0
	var hand_local := blanket.to_local(_bone(prefix+"Hand"))
	var target_x := clampf(hand_local.x,bounds.get_center().x-0.19,bounds.get_center().x+0.19)
	var best := INF
	var grab := 0
	for index in range(points.size()):
		var distance := absf(rest[index].x-target_x)+absf(rest[index].z-bounds.position.z)*3.0
		if distance < best:
			best = distance
			grab = index
	var target := blanket.to_global(points[grab])+Vector3.UP*0.012
	target = _bone(prefix+"Hand").lerp(target,weight)
	ARM_POSE._solve(_hips,ARM_POSE._bone(_hips,prefix+"Arm"),ARM_POSE._bone(_hips,prefix+"ForeArm"),ARM_POSE._bone(_hips,prefix+"Hand"),target,_across*sign_value-_axis*0.15+Vector3.UP*0.2)
	for finger: String in ["Thumb", "Index", "Middle", "Ring", "Pinky"]:
		for joint in range(1,4):
			var bone := ARM_POSE._bone(_hips,prefix+"Hand"+finger+str(joint))
			if bone>=0: _hips.set_bone_pose_rotation(bone,_hips.get_bone_pose_rotation(bone)*Quaternion(Vector3.RIGHT,weight*0.55))
	var wrist := _bone(prefix+"Hand")
	if weight>=0.999:
		_duvet.pin_grip(grab,blanket.to_local(wrist-Vector3.UP*0.012),1.0)
	var actual: PackedVector3Array = blanket.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	grip_report = {"hand":prefix,"gap":wrist.distance_to(blanket.to_global(actual[grab])),"weight":weight}

func _process(delta: float) -> void:
	var active := "C02-bed-cover"
	if _owner != null:
		if bool(_owner.call("observer_presentation_paused")): return
		active = str((_owner.call("observer_camera_catalog") as Dictionary).get("active_id",""))
	var selected := "back" if active=="sleep-back" else ("side-right" if active=="sleep-right" else "side-left")
	if selected != mode: set_mode(selected)
	if active != _active:
		_active = active
		_elapsed = 0.0
	_elapsed += delta
	sample_bedding(_elapsed if active.begins_with("sleep-") else 7.0+fmod(_elapsed,4.2))
	if animation_stage != _last_stage:
		_last_stage = animation_stage
		print("SLEEP_STAGE ", JSON.stringify({"mode": mode,"stage": animation_stage,"seconds": fposmod(_elapsed,CYCLE)}))
