extends Node3D
## Local visual traversal of the existing world; no resident or animation edits.
var actor
var nest: Node3D
var camera: Camera3D
var route: Array = []
var index := 0
var blocked := ""
var running := false
var waiting := false
var pause_each := false
var started := false
var world_ready := false
var speed := 2
var pause_clock := 0
var label: Label
var details: Label
var play: Button
var pause_button: Button
var follow := true
var yaw := 0.65
var pitch := 0.32
var distance := 3.5
var focus := Vector3.ZERO
var effective_speed := 2
var slow_seconds := 0.0
var recovery_seconds := 0.0
var sample_seconds := 0.0
var sampled_frames := 0
var display_fps := 0.0
var performance_label: Label
var speed_select: OptionButton
var frame_clock_usec := 0
var history: Array = []
var original_ticks := 60
var performance_probe: Node
var profile_camera_override := false

func setup(world: Node3D, characters: Node3D) -> void:
	process_mode=Node.PROCESS_MODE_ALWAYS
	original_ticks=Engine.physics_ticks_per_second
	nest=world
	controls()
	var load_deadline=Time.get_ticks_msec()+120000
	while world.get("_estate_physics")==null:
		if Time.get_ticks_msec()>load_deadline:
			blocked="Scene loading timed out; reload to retry";return
		await get_tree().process_frame
	world.set_process_unhandled_input(false)
	world.set_observation_hud_visible(false)
	if not world.bake_navigation():
		blocked="Navigation bake unavailable; precompiled="+str(world.get("_estate_physics").loaded_precompiled);return
	if not await world.wait_for_navigation_sync(30.0):
		blocked="Navigation synchronization timed out";return
	world.validate_navigation_anchors()
	# This standalone daytime tour has no observer time snapshot.
	# Reuse the accepted daytime policy instead of enabling every night fixture.
	world.apply_environment_state("nest/environment",false,false)
	build_route()
	actor=load("res://characters/tovren/tovren.tscn").instantiate()
	actor.install_shared_animations=false
	characters.add_child(actor)
	var player: AnimationPlayer=actor.get_node("AnimationPlayer")
	player.add_animation_library("",preload("res://runtime/actor/chair_clip_sequence.gd").locomotion_for(actor))
	# The only placement: initial spawn. Retries keep the actual failed position.
	actor.configure("local-navigation-tour",world.resolve_anchor("central-04/activity").global_position)
	actor.navigation_terminal.connect(accept_terminal)
	camera=Camera3D.new();add_child(camera)
	camera.near=0.05;camera.fov=65
	focus=actor.global_position+Vector3.UP*0.8
	camera.position=focus+Vector3(2,1,2);camera.make_current()
	await get_tree().physics_frame
	await get_tree().physics_frame
	world_ready=true;play.disabled=false
	if OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('profile')"))=="1":
		performance_probe=load("res://runtime/lab/estate_performance_probe.gd").new()
		add_child(performance_probe);performance_probe.setup(world)
	set_speed(2)
	if OS.has_feature("web") and str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('speed')"))=="4":set_speed(4)
	if OS.has_feature("web") and bool(JavaScriptBridge.eval("new URLSearchParams(location.search).get('autoplay') === '1'")):
		start_or_continue()

func anchor(title: String,id: String) -> void:
	var marker=nest.resolve_anchor(id)
	route.append({"title":title,"point":marker.global_position if marker!=null else Vector3.INF})

func outdoor(title: String,point: Vector3,max_snap: float=1.2) -> void:
	var map=get_world_3d().navigation_map
	var target=NavigationServer3D.map_get_closest_point(map,point)
	var access=nest.get_node("Generated/EstatePhysics").outdoor_access
	var valid=target.distance_to(point)<max_snap and access.contains_outdoor_point(Vector2(target.x,target.z))
	route.append({"title":title,"point":target,"invalid":"道路取样不在可行走区域" if not valid else ""})

func build_route() -> void:
	for level in [3,2,1]:anchor("主楼下楼 → %d 层"%level,"central-%02d/activity"%level)
	anchor("房间 M01 · 床边","dorm-01/bed-01")
	anchor("房间 M01 · 桌椅旁","dorm-01/chair-01")
	anchor("房间 M01 · 上露台","terrace-01/activity")
	anchor("房间 M01 · 下楼","dorm-01/bed-01")
	anchor("退出 M01，返回大厅","central-01/activity")
	anchor("房间 M05 · 床边","dorm-05/bed-01")
	anchor("房间 M05 · 绕家具到桌旁","dorm-05/chair-01")
	anchor("退出 M05，返回大厅","central-01/activity")
	anchor("穿过花园门 → 庭院","courtyard/activity")
	# The ring is authored around the origin; snap only nearby road points.
	for i in range(13):
		var angle=PI/2.0+TAU*i/12.0
		outdoor("环路 %d / 12"%mini(i+1,12),Vector3(cos(angle)*20.0,0.18,sin(angle)*20.0),4.0)
	var trail_index=0
	for mesh: MeshInstance3D in nest.find_children("*","MeshInstance3D",true,false):
		var paths: Array=mesh.get_meta("extras",{}).get("forest_trail_paths",[])
		for path: Array in paths:
			trail_index+=1
			var previous=Vector3.INF
			for i in range(path.size()):
				var p=Vector3(float(path[i][0]),float(path[i][1]),float(path[i][2]))
				if i!=path.size()-1 and p.distance_to(previous)<5.0:continue
				outdoor("林间%s · %d"%["主路" if trail_index==1 else "支路",i+1],p)
				previous=p
	outdoor("草坪 · 入口",Vector3(-24,-0.02,34))
	outdoor("草坪 · 返回",Vector3(-30,-0.02,30))
	anchor("湖边可达观景点","courtyard/lakeside-seat")
	anchor("返回庭院入口","courtyard/activity")

func controls() -> void:
	var layer=CanvasLayer.new();add_child(layer)
	if OS.has_feature("web"):layer.scale=Vector2.ONE*float(JavaScriptBridge.eval("window.devicePixelRatio || 1"))
	var panel=PanelContainer.new();panel.position=Vector2(10,10);layer.add_child(panel)
	var box=VBoxContainer.new();panel.add_child(box)
	var theme=Theme.new();theme.default_font=load("res://ui/fonts/NotoSansSC-ObservationHUD.ttf");box.theme=theme
	label=Label.new();label.custom_minimum_size.x=320;box.add_child(label)
	var row=HBoxContainer.new();box.add_child(row)
	play=Button.new();play.text="开始巡游";play.disabled=true;row.add_child(play)
	play.pressed.connect(start_or_continue)
	pause_button=Button.new();pause_button.text="暂停";row.add_child(pause_button)
	pause_button.pressed.connect(toggle_pause)
	var speeds=OptionButton.new();row.add_child(speeds);speed_select=speeds
	for value in [1,2,4]:speeds.add_item("%d 倍速"%value,value)
	speeds.select(1);speeds.item_selected.connect(func(i: int):set_speed(speeds.get_item_id(i)))
	var check=CheckButton.new();check.text="每站暂停";box.add_child(check)
	check.toggled.connect(func(value: bool):pause_each=value)
	var follow_button=Button.new();follow_button.text="恢复跟随角度";box.add_child(follow_button)
	follow_button.pressed.connect(func():follow=true;yaw=0.65;pitch=0.32;distance=3.5)
	performance_label=Label.new();box.add_child(performance_label)
	details=Label.new();details.custom_minimum_size.x=320;details.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART;box.add_child(details)

func set_speed(value: int) -> void:
	speed=clampi(value,1,4)
	if speed_select!=null:speed_select.select([1,2,4].find(speed))
	slow_seconds=0.0
	recovery_seconds=0.0
	apply_effective_speed(speed)

func apply_effective_speed(value: int) -> void:
	effective_speed=value
	# Keep each simulated collision step at 1/60 s, even when overloaded.
	Engine.physics_ticks_per_second=60*effective_speed
	Engine.time_scale=float(effective_speed)

func adjust_for_framerate(fps: float, seconds: float) -> void:
	var limit := 1 if fps<20.0 else (2 if fps<35.0 else 4)
	if limit<effective_speed:
		slow_seconds+=seconds
		recovery_seconds=0.0
		if slow_seconds>=2.0:
			apply_effective_speed(mini(speed,limit))
			slow_seconds=0.0
	elif fps>=55.0 and effective_speed<speed:
		slow_seconds=0.0
		recovery_seconds+=seconds
		if recovery_seconds>=10.0:
			apply_effective_speed(mini(speed,effective_speed*2))
			recovery_seconds=0.0
	else:
		slow_seconds=0.0
		recovery_seconds=0.0

func start_or_continue() -> void:
	if not world_ready or running or get_tree().paused:return
	if index>=route.size():return
	blocked="";waiting=false;started=true
	var stage: Dictionary=route[index]
	if not str(stage.get("invalid","")).is_empty() or not (stage.point as Vector3).is_finite():
		blocked=str(stage.get("invalid","缺少目标"));return
	running=true
	if not actor.move_to("leg-%d"%index,stage.point,180.0):
		running=false;blocked="当前目标没有可行路径，停在实际位置"

func accept_terminal(id: String,status: String,reason: String) -> void:
	if id!="leg-%d"%index:return
	running=false
	var arrived: bool=status=="completed" and actor.global_position.distance_to(route[index].point)<0.6
	history.append({"stage":index,"status":status,"reason":reason,"position":str(actor.global_position)})
	print("NAVIGATION_TOUR ",JSON.stringify(history.back()))
	if not arrived:
		blocked="%s：%s\n位置 %s"%[status,reason,actor.global_position]
		return
	index+=1;waiting=pause_each

func toggle_pause() -> void:
	if not world_ready:return
	get_tree().paused=not get_tree().paused
	if get_tree().paused:pause_clock=Time.get_ticks_msec()
	elif not actor.active_command_id.is_empty():actor.set("_deadline_msec",int(actor.get("_deadline_msec"))+Time.get_ticks_msec()-pause_clock)
	pause_button.text="继续播放" if get_tree().paused else "暂停"

func _process(_delta: float) -> void:
	# Camera/UI pacing follows wall time; simulated time is only for the world.
	var now := Time.get_ticks_usec()
	var wall_delta := float(now-frame_clock_usec)/1000000.0 if frame_clock_usec>0 else 0.0
	frame_clock_usec=now
	if world_ready and not get_tree().paused:
		sample_seconds+=wall_delta
		sampled_frames+=1
		if sample_seconds>=1.0:
			display_fps=sampled_frames/sample_seconds
			adjust_for_framerate(display_fps,sample_seconds)
			sample_seconds=0.0;sampled_frames=0
	if performance_probe!=null:
		performance_probe.sample_frame()
	if performance_label!=null:
		performance_label.text="FPS %.0f | selected %dx | actual %dx"%[display_fps,speed,effective_speed]
		if performance_probe!=null:performance_label.text+="\n"+performance_probe.status()
	if label!=null:
		label.text="导航巡游 · 两间代表房间\n%d / %d 站 · %d 倍速\n%s"%[index,route.size(),speed,str(route[index].title) if index<route.size() else "巡游结束"]
		details.text=("停在现场："+blocked) if not blocked.is_empty() else ("加载真实场景…" if not world_ready else "拖拽旋转 · 滚轮缩放 · Space 暂停\n"+("下一站："+str(route[index+1].title) if index+1<route.size() else ""))
		play.text="重试当前站" if not blocked.is_empty() else ("继续下一站" if waiting else "开始巡游")
		play.disabled=not world_ready or running or index>=route.size()
	if not world_ready:return
	if started and not running and not waiting and blocked.is_empty() and index<route.size() and not get_tree().paused:start_or_continue()
	if get_tree().paused or profile_camera_override:return
	var target=actor.global_position+Vector3.UP*0.8
	var amount=1.0-exp(-wall_delta*5.0)
	focus=focus.lerp(target,amount)
	if follow and actor.velocity.length()>0.1:
		var desired_yaw=atan2(-actor.velocity.x,-actor.velocity.z)
		yaw=lerp_angle(yaw,desired_yaw,1.0-exp(-wall_delta*1.5))
	var offset=Vector3(sin(yaw)*cos(pitch),sin(pitch),cos(yaw)*cos(pitch))*distance
	var desired=target+offset
	var query=PhysicsRayQueryParameters3D.create(target,desired,1,[actor.get_rid()])
	var hit=get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty():desired=hit.position+hit.normal*0.12
	camera.global_position=camera.global_position.lerp(desired,amount)
	camera.look_at(focus)

func _unhandled_input(event: InputEvent) -> void:
	if not world_ready:return
	if performance_probe!=null and event is InputEventKey and event.pressed and not event.echo:
		if event.keycode==KEY_F6:performance_probe.cycle_view();return
		if event.keycode==KEY_F7:performance_probe.toggle_samples();return
		if event.keycode==KEY_F8:performance_probe.toggle_shadows();return
		if event.keycode==KEY_F9:performance_probe.toggle_day();return
		if event.keycode==KEY_F10:performance_probe.toggle_shadow_budget();return
		if event.keycode==KEY_F11:performance_probe.toggle_retina_budget();return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode==KEY_SPACE:
		toggle_pause();get_viewport().set_input_as_handled();return
	if event is InputEventMouseMotion and event.button_mask&MOUSE_BUTTON_MASK_LEFT:
		follow=false;yaw-=event.relative.x*0.006;pitch=clampf(pitch+event.relative.y*0.004,-0.1,0.65)
	if event is InputEventMouseButton and event.pressed:
		if event.button_index==MOUSE_BUTTON_WHEEL_UP:distance=maxf(1.2,distance-0.3)
		if event.button_index==MOUSE_BUTTON_WHEEL_DOWN:distance=minf(7.0,distance+0.3)

func _exit_tree() -> void:
	Engine.time_scale=1.0;Engine.physics_ticks_per_second=original_ticks
	if get_tree()!=null:get_tree().paused=false
