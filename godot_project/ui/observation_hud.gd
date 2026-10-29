class_name ObservationHUD
extends CanvasLayer

signal view_selected(index: int)

@onready var _selector: OptionButton = $Margin/Panel/Controls/CameraSelector
@onready var _overview_button: Button = $Margin/Panel/Controls/OverviewButton
@onready var _previous_button: Button = $Margin/Panel/Controls/PreviousButton
@onready var _next_button: Button = $Margin/Panel/Controls/NextButton
var _phase_selector: OptionButton
var _lighting_views: Array[Dictionary] = []
var _lighting_cameras: PackedStringArray = []
const LIGHTING_PHASES := ["day", "night", "quiet"]
const LIGHTING_CAMERAS := {"overview": "全园总览", "central": "主楼正面", "living": "一层室内", "middle": "二层室内", "upper": "三层室内", "plaza": "小广场", "ring": "环形路", "forest": "林间小路", "lake": "湖与喷泉", "seats": "湖边座椅", "bedroom": "卧室", "terrace": "露台"}


func _ready() -> void:
	if Engine.is_editor_hint():
		visible = false
		return
	_overview_button.pressed.connect(_select_overview)
	_previous_button.pressed.connect(_select_previous)
	_next_button.pressed.connect(_select_next)
	_selector.item_selected.connect(_select_from_menu)


func set_views(labels: PackedStringArray, selected_index: int = 0) -> void:
	_lighting_views.clear()
	_lighting_cameras.clear()
	_set_lighting_controls(false)
	_selector.clear()
	for label in labels:
		_selector.add_item(label)
	set_selected_view(selected_index)
	_update_enabled_state()


func set_selected_view(index: int) -> void:
	if not _lighting_views.is_empty():
		var parts := str(_lighting_views[clampi(index, 0, _lighting_views.size() - 1)].id).split("-")
		_phase_selector.select(LIGHTING_PHASES.find(parts[-1]))
		_selector.select(_lighting_cameras.find(parts[-2]))
		return
	if _selector.item_count == 0:
		return
	_selector.select(clampi(index, 0, _selector.item_count - 1))


func _select_overview() -> void:
	_emit_selection(0)


func _select_previous() -> void:
	if _selector.item_count == 0:
		return
	_emit_selection(posmod(_selector.selected - 1, _selector.item_count))


func _select_next() -> void:
	if _selector.item_count == 0:
		return
	_emit_selection(posmod(_selector.selected + 1, _selector.item_count))


func _select_from_menu(index: int) -> void:
	if not _lighting_views.is_empty():
		_select_lighting_view(index, _phase_selector.selected)
		return
	_emit_selection(index)


func set_lighting_views(views: Array[Dictionary]) -> void:
	_lighting_views = views.duplicate()
	_lighting_cameras.clear()
	_set_lighting_controls(true)
	_selector.clear()
	for view: Dictionary in views:
		var camera := str(view.id).split("-")[-2]
		if camera in _lighting_cameras: continue
		_lighting_cameras.append(camera)
		_selector.add_item(str(LIGHTING_CAMERAS.get(camera, camera)))
	set_selected_view(0)


func _set_lighting_controls(enabled: bool) -> void:
	if enabled and _phase_selector == null:
		_phase_selector = OptionButton.new()
		_phase_selector.name = "PhaseSelector"
		_phase_selector.custom_minimum_size = Vector2(176, 34)
		_phase_selector.focus_mode = Control.FOCUS_NONE
		_phase_selector.tooltip_text = "选择时段，保留当前视角"
		for label: String in ["白天 06:00-18:00", "上半夜 18:00-24:00", "下半夜 00:00-06:00"]:
			_phase_selector.add_item(label)
		_selector.get_parent().add_child(_phase_selector)
		_selector.get_parent().move_child(_phase_selector, 0)
		_phase_selector.item_selected.connect(_select_phase)
	if _phase_selector != null: _phase_selector.visible = enabled
	for control: Control in [$Margin/Panel/Controls/ViewLabel, _overview_button, _previous_button, _next_button]:
		control.visible = not enabled
	_selector.custom_minimum_size.x = 150 if enabled else 220
	_selector.tooltip_text = "选择视角，保留当前时段" if enabled else "选择观察房间"
	$Margin.offset_right = 376 if enabled else 476


func _select_phase(index: int) -> void:
	_select_lighting_view(_selector.selected, index)


func _select_lighting_view(camera: int, phase: int) -> void:
	var id: String = "lighting-v4-" + _lighting_cameras[camera] + "-" + LIGHTING_PHASES[phase]
	for index in _lighting_views.size():
		if _lighting_views[index].id == id:
			_emit_selection(index)
			return


func _emit_selection(index: int) -> void:
	set_selected_view(index)
	view_selected.emit(index)


func _update_enabled_state() -> void:
	var has_multiple_views := _selector.item_count > 1
	_overview_button.disabled = _selector.item_count == 0
	_previous_button.disabled = not has_multiple_views
	_next_button.disabled = not has_multiple_views
