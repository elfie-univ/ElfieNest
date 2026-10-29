extends Control
## A single isolated Godot viewport and one replaceable animation fixture.
const CATALOG := preload("res://runtime/lab/estate_animation_picker_catalog.gd")
const RUNNER := preload("res://runtime/lab/estate_animation_picker_runner.gd")
var entries := CATALOG.entries()
var source_entries := CATALOG.source_entries()
var choices: OptionButton
var variant_choices: OptionButton
var water_time: OptionButton
var source_choices: OptionButton
var status: Label
var preview: SubViewport
var runner: Node3D
var _requested: Dictionary = {}
var _pending := false
var _paused_preview := false
var _pause_button: Button
var _deadline := 0
var _pause_started := 0

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var container := SubViewportContainer.new()
	container.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	container.stretch = true
	add_child(container)
	preview = SubViewport.new()
	preview.own_world_3d = true
	preview.size = Vector2i(900,700)
	preview.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	container.add_child(preview)
	var layer := CanvasLayer.new()
	add_child(layer)
	if OS.has_feature("web"): layer.scale = Vector2.ONE * float(JavaScriptBridge.eval("window.devicePixelRatio || 1"))
	var panel := PanelContainer.new()
	panel.position = Vector2(10,10)
	layer.add_child(panel)
	var box := VBoxContainer.new()
	panel.add_child(box)
	var theme := Theme.new()
	theme.default_font = load("res://ui/fonts/NotoSansSC-ObservationHUD.ttf")
	box.theme = theme
	var title := Label.new()
	title.text = "动画单项预览 / 选择即播放"
	box.add_child(title)
	choices = OptionButton.new()
	choices.custom_minimum_size.x = 335
	choices.fit_to_longest_item = false
	choices.get_popup().max_size.y = 450
	for index in range(entries.size()): choices.add_item(entries[index]["title"],index)
	choices.item_selected.connect(select_animation)
	box.add_child(choices)
	variant_choices = OptionButton.new()
	variant_choices.item_selected.connect(select_variant)
	box.add_child(variant_choices)
	water_time = OptionButton.new()
	water_time.add_item("白天")
	water_time.add_item("夜间")
	water_time.item_selected.connect(select_water_time)
	box.add_child(water_time)
	var source_title := Label.new()
	source_title.text = "单独动作"
	box.add_child(source_title)
	source_choices = OptionButton.new()
	source_choices.custom_minimum_size.x = 335
	source_choices.fit_to_longest_item = false
	source_choices.get_popup().max_size.y = 450
	source_choices.add_item("请选择单独动作…")
	for item: Dictionary in source_entries: source_choices.add_item(item["title"])
	source_choices.item_selected.connect(func(index: int) -> void:
		if index > 0: select_source_animation(index - 1))
	box.add_child(source_choices)
	var row := HBoxContainer.new()
	box.add_child(row)
	var replay := Button.new()
	replay.text = "重播所选"
	replay.pressed.connect(replay_selected)
	row.add_child(replay)
	_pause_button = Button.new()
	_pause_button.text = "暂停"
	_pause_button.pressed.connect(toggle_pause)
	row.add_child(_pause_button)
	status = Label.new()
	status.custom_minimum_size.x = 335
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.text = "请选择动画"
	box.add_child(status)
	var note := Label.new()
	note.text = "9 个情景组；25 个源动作及点头、摇头\n选择即播放，可切换场景和睡姿"
	note.add_theme_font_size_override("font_size",12)
	box.add_child(note)
	choices.grab_focus()
	select_animation(0)

func select_animation(index: int) -> void:
	if index<0 or index>=entries.size(): return
	choices.select(index)
	source_choices.select(0)
	variant_choices.clear()
	for option: Dictionary in CATALOG.variants(entries[index]["id"]):
		variant_choices.add_item(option["title"])
	variant_choices.visible = variant_choices.item_count > 0
	water_time.visible = entries[index]["id"] == "water"
	water_time.select(0)
	_queue_group()

func select_variant(index: int) -> void:
	if index < 0 or index >= variant_choices.item_count: return
	variant_choices.select(index)
	source_choices.select(0)
	_queue_group()

func select_water_time(index: int) -> void:
	if not water_time.visible or index < 0 or index > 1: return
	water_time.select(index)
	source_choices.select(0)
	_queue_group()

func _queue_group() -> void:
	_queue_preview(CATALOG.resolve_entry(entries[choices.selected]["id"], maxi(0, variant_choices.selected), water_time.selected == 1))

func select_source_animation(index: int) -> void:
	if index < 0 or index >= source_entries.size(): return
	source_choices.select(index + 1)
	_queue_preview(source_entries[index])

func replay_selected() -> void:
	_queue_preview(_requested)

func _queue_preview(value: Dictionary) -> void:
	if value.is_empty(): return
	_requested = value.duplicate()
	if not _pending:
		_pending=true
		call_deferred("_replace_preview")

func _replace_preview() -> void:
	_pending=false
	# Destroy the coroutine owner, its actor, geometry, colliders and effects.
	# A late signal from the previous sample cannot continue into the new one.
	if is_instance_valid(runner): runner.free()
	preview.render_target_update_mode=SubViewport.UPDATE_ALWAYS
	_paused_preview=false
	_pause_button.text="暂停"
	status.text="准备所选场景…"
	_deadline=Time.get_ticks_msec()+30000
	runner=RUNNER.new()
	preview.add_child(runner)
	runner.start(_requested)

func toggle_pause() -> void:
	if not is_instance_valid(runner) or runner.get("_actor")==null: return
	_paused_preview=not _paused_preview
	if _paused_preview: _pause_started=Time.get_ticks_msec()
	else:
		var actor: ElfieActor=runner.get("_actor")
		if not actor.active_command_id.is_empty():
			actor.set("_deadline_msec",int(actor.get("_deadline_msec"))+Time.get_ticks_msec()-_pause_started)
	runner.set("_paused",_paused_preview)
	runner.process_mode=Node.PROCESS_MODE_DISABLED if _paused_preview else Node.PROCESS_MODE_INHERIT
	preview.render_target_update_mode=SubViewport.UPDATE_DISABLED if _paused_preview else SubViewport.UPDATE_ALWAYS
	_pause_button.text="继续" if _paused_preview else "暂停"

func _process(_delta: float) -> void:
	if not is_instance_valid(runner): return
	status.text=str(runner.get("_phase"))
	if Time.get_ticks_msec()>_deadline and runner.get("_actor")==null:
		runner.free()
		status.text="所选场景准备超时，请选择其他项或重播"
