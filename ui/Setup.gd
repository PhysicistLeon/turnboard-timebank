extends Control

@onready var players_editor: VBoxContainer = $VBox/PlayersEditor
@onready var err: Label = $VBox/Error

@onready var bank: SpinBox = $VBox/GridRules/BankMs
@onready var cd: SpinBox = $VBox/GridRules/CooldownMs
@onready var warn: SpinBox = $VBox/GridRules/WarnEveryMs

var _selected_index: int = -1

func _ready() -> void:
	GameController.state_changed.connect(_render)

	$VBox/HBox1/AddBtn.pressed.connect(_on_add_pressed)
	$VBox/HBox1/RemoveBtn.pressed.connect(_on_remove_pressed)
	$VBox/HBox1/UpBtn.pressed.connect(_on_move_up_pressed)
	$VBox/HBox1/DownBtn.pressed.connect(_on_move_down_pressed)
	$VBox/StartBtn.pressed.connect(_on_start_pressed)

	bank.min_value = 10
	bank.max_value = 24 * 60 * 60
	cd.min_value = 0
	cd.max_value = 300
	warn.min_value = 1
	warn.max_value = 3600

	_render(GameController.state)

func _render(s: Model.GameState) -> void:
	if _selected_index >= s.order.size():
		_selected_index = s.order.size() - 1

	for child in players_editor.get_children():
		child.queue_free()

	for i in range(s.order.size()):
		var player_name: String = s.order[i]
		var row := HBoxContainer.new()
		row.theme_override_constants.separation = 8
		row.custom_minimum_size = Vector2(0, 72)

		var select_btn := Button.new()
		select_btn.text = "●" if i == _selected_index else "○"
		select_btn.custom_minimum_size = Vector2(56, 56)
		select_btn.theme_override_font_sizes.font_size = 24
		select_btn.pressed.connect(_on_row_selected.bind(i))
		row.add_child(select_btn)

		var name_edit := LineEdit.new()
		name_edit.text = player_name
		name_edit.custom_minimum_size = Vector2(260, 56)
		name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		name_edit.theme_override_font_sizes.font_size = 28
		name_edit.text_submitted.connect(_on_name_submitted.bind(i))
		name_edit.focus_entered.connect(_on_row_selected.bind(i))
		row.add_child(name_edit)

		var color_btn := ColorPickerButton.new()
		color_btn.custom_minimum_size = Vector2(120, 56)
		color_btn.color = (s.players[player_name] as Model.Player).color
		color_btn.color_changed.connect(_on_color_changed.bind(i))
		color_btn.pressed.connect(_on_row_selected.bind(i))
		row.add_child(color_btn)

		var bms: int = int(s.bank_ms.get(player_name, s.rules.bank_initial_ms))
		var bank_lbl := Label.new()
		bank_lbl.text = Util.ms_to_mmss(bms)
		bank_lbl.theme_override_font_sizes.font_size = 28
		bank_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		bank_lbl.custom_minimum_size = Vector2(120, 56)
		row.add_child(bank_lbl)

		players_editor.add_child(row)

	bank.value = int(round(s.rules.bank_initial_ms / 1000.0))
	cd.value = int(round(s.rules.cooldown_ms / 1000.0))
	warn.value = int(round(s.rules.warn_every_ms / 1000.0))

func _on_add_pressed() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	var base := "P"
	var i := 1
	var player_name := "%s%d" % [base, i]
	while s.players.has(player_name):
		i += 1
		player_name = "%s%d" % [base, i]
	var p := Model.Player.new()
	p.name = player_name
	p.color = Color.WHITE
	s.players[player_name] = p
	s.order.append(player_name)
	s.bank_ms[player_name] = s.rules.bank_initial_ms
	_selected_index = s.order.size() - 1
	_render(s)

func _on_remove_pressed() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	if _selected_index < 0 or _selected_index >= s.order.size():
		return
	var player_name: String = s.order[_selected_index]
	s.players.erase(player_name)
	s.bank_ms.erase(player_name)
	s.order.remove_at(_selected_index)
	if _selected_index >= s.order.size():
		_selected_index = s.order.size() - 1
	_render(s)

func _on_move_up_pressed() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	if _selected_index <= 0 or _selected_index >= s.order.size():
		return
	var a: String = s.order[_selected_index - 1]
	s.order[_selected_index - 1] = s.order[_selected_index]
	s.order[_selected_index] = a
	_selected_index -= 1
	_render(s)

func _on_move_down_pressed() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	if _selected_index < 0 or _selected_index >= s.order.size() - 1:
		return
	var a: String = s.order[_selected_index + 1]
	s.order[_selected_index + 1] = s.order[_selected_index]
	s.order[_selected_index] = a
	_selected_index += 1
	_render(s)

func _on_row_selected(i: int) -> void:
	_selected_index = i
	_render(GameController.state)

func _on_name_submitted(new_name: String, i: int) -> void:
	var s: Model.GameState = GameController.state
	if i < 0 or i >= s.order.size():
		return
	var old_name: String = s.order[i]
	var trimmed: String = new_name.strip_edges()
	if trimmed == "" or trimmed == old_name:
		_render(s)
		return
	if s.players.has(trimmed):
		err.text = "Имя уже занято"
		_render(s)
		return

	var p: Model.Player = s.players[old_name]
	s.players.erase(old_name)
	p.name = trimmed
	s.players[trimmed] = p

	var bms: int = int(s.bank_ms.get(old_name, s.rules.bank_initial_ms))
	s.bank_ms.erase(old_name)
	s.bank_ms[trimmed] = bms
	s.order[i] = trimmed
	err.text = ""
	_render(s)

func _on_color_changed(new_color: Color, i: int) -> void:
	var s: Model.GameState = GameController.state
	if i < 0 or i >= s.order.size():
		return
	var player_name: String = s.order[i]
	if not s.players.has(player_name):
		return
	var p: Model.Player = s.players[player_name]
	p.color = new_color

func _on_start_pressed() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	s.rules.bank_initial_ms = int(bank.value) * 1000
	s.rules.cooldown_ms = int(cd.value) * 1000
	s.rules.warn_every_ms = int(warn.value) * 1000

	for player_name in s.players.keys():
		s.bank_ms[player_name] = s.rules.bank_initial_ms

	err.text = ""
	GameController.dispatch({"type": Const.CMD_START_GAME})

