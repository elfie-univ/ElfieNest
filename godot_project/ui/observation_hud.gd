class_name ObservationHUD
extends CanvasLayer

signal view_selected(index: int)

@onready var _selector: OptionButton = $Margin/Panel/Controls/CameraSelector
@onready var _overview_button: Button = $Margin/Panel/Controls/OverviewButton
@onready var _previous_button: Button = $Margin/Panel/Controls/PreviousButton
@onready var _next_button: Button = $Margin/Panel/Controls/NextButton


func _ready() -> void:
	if Engine.is_editor_hint():
		visible = false
		return
	_overview_button.pressed.connect(_select_overview)
	_previous_button.pressed.connect(_select_previous)
	_next_button.pressed.connect(_select_next)
	_selector.item_selected.connect(_select_from_menu)


func set_views(labels: PackedStringArray, selected_index: int = 0) -> void:
	_selector.clear()
	for label in labels:
		_selector.add_item(label)
	set_selected_view(selected_index)
	_update_enabled_state()


func set_selected_view(index: int) -> void:
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
	_emit_selection(index)


func _emit_selection(index: int) -> void:
	set_selected_view(index)
	view_selected.emit(index)


func _update_enabled_state() -> void:
	var has_multiple_views := _selector.item_count > 1
	_overview_button.disabled = _selector.item_count == 0
	_previous_button.disabled = not has_multiple_views
	_next_button.disabled = not has_multiple_views
