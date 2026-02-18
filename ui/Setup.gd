extends Control

@onready var rows_root: VBoxContainer = $VBox/PlayersScroll/PlayersRows
@onready var err: Label = $VBox/Error

@onready var bank: SpinBox = $VBox/GridRules/BankMs
@onready var cd: SpinBox = $VBox/GridRules/CooldownMs
@onready var warn: SpinBox = $VBox/GridRules/WarnEveryMs

var _selected_index: int = 0

func _ready() -> void:
	GameController.state_changed.connect(_render)

	$VBox/HBox1/AddBtn.pressed.connect(_add_player)
	$VBox/HBox1/RemoveBtn.pressed.connect(_remove_player)
	$VBox/HBox1/UpBtn.pressed.connect(_move_up)
	$VBox/HBox1/DownBtn.pressed.connect(_move_down)

	$VBox/StartBtn.pressed.connect(_start)

	bank.min_value = 10
	bank.max_value = 24 * 60 * 60
	cd.min_value = 0
	cd.max_value = 300
	warn.min_value = 1
	warn.max_value = 3600

	_render(GameController.state)

func _render(s: Model.GameState) -> void:
	for child in rows_root.get_children():
		child.queue_free()

	if s.order.is_empty():
		_selected_index = -1
	else:
		_selected_index = clampi(_selected_index, 0, s.order.size() - 1)

	for idx in range(s.order.size()):
		var player_name: String = s.order[idx]
		var pl: Model.Player = s.players[player_name]
		var bms: int = int(s.bank_ms.get(player_name, s.rules.bank_initial_ms))
		rows_root.add_child(_build_player_row(idx, pl, bms))

	bank.value = int(round(s.rules.bank_initial_ms / 1000.0))
	cd.value = int(round(s.rules.cooldown_ms / 1000.0))
	warn.value = int(round(s.rules.warn_every_ms / 1000.0))

func _build_player_row(idx: int, player: Model.Player, bank_ms: int) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.custom_minimum_size = Vector2(0, 76)
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.alignment = BoxContainer.ALIGNMENT_BEGIN
	row.add_theme_constant_override("separation", 10)

	var select_btn := Button.new()
	select_btn.text = "●" if idx == _selected_index else "○"
	select_btn.custom_minimum_size = Vector2(60, 64)
	select_btn.add_theme_font_size_override("font_size", 26)
	select_btn.pressed.connect(func() -> void:
		_selected_index = idx
		GameController.play_ui_click()
		_render(GameController.state)
	)
	row.add_child(select_btn)

	var name_edit := LineEdit.new()
	name_edit.custom_minimum_size = Vector2(260, 64)
	name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_edit.text = player.name
	name_edit.add_theme_font_size_override("font_size", 28)
	name_edit.text_submitted.connect(func(_submitted: String) -> void:
		_try_rename_player(player.name, name_edit.text)
	)
	name_edit.focus_exited.connect(func() -> void:
		_try_rename_player(player.name, name_edit.text)
	)
	row.add_child(name_edit)

	var color_btn := ColorPickerButton.new()
	color_btn.custom_minimum_size = Vector2(120, 64)
	color_btn.color = player.color
	color_btn.color_changed.connect(func(new_color: Color) -> void:
		if GameController.state.players.has(player.name):
			(GameController.state.players[player.name] as Model.Player).color = new_color
		GameController.play_ui_click()
	)
	row.add_child(color_btn)

	var bank_label := Label.new()
	bank_label.custom_minimum_size = Vector2(150, 64)
	bank_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	bank_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	bank_label.add_theme_font_size_override("font_size", 26)
	bank_label.text = Util.ms_to_mmss(bank_ms)
	row.add_child(bank_label)

	return row

func _try_rename_player(old_name: String, raw_new: String) -> void:
	var s: Model.GameState = GameController.state
	if not s.players.has(old_name):
		return

	var new_name: String = raw_new.strip_edges()
	if new_name == "":
		err.text = "Имя игрока не может быть пустым"
		_render(s)
		return
	if new_name == old_name:
		return
	if s.players.has(new_name):
		err.text = "Игрок с таким именем уже существует"
		_render(s)
		return

	var pl: Model.Player = s.players[old_name]
	s.players.erase(old_name)
	pl.name = new_name
	s.players[new_name] = pl

	var b: int = int(s.bank_ms.get(old_name, s.rules.bank_initial_ms))
	s.bank_ms.erase(old_name)
	s.bank_ms[new_name] = b

	for i in range(s.order.size()):
		if s.order[i] == old_name:
			s.order[i] = new_name

	err.text = ""
	GameController.play_ui_click()
	_render(s)

func _add_player() -> void:
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
	p.color = Color.from_hsv(randf(), 0.55, 0.95)
	s.players[player_name] = p
	s.order.append(player_name)
	s.bank_ms[player_name] = s.rules.bank_initial_ms
	_selected_index = s.order.size() - 1
	_render(s)

func _remove_player() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	if s.order.is_empty() or _selected_index < 0:
		return
	var i: int = clampi(_selected_index, 0, s.order.size() - 1)
	var player_name: String = s.order[i]
	s.players.erase(player_name)
	s.bank_ms.erase(player_name)
	s.order.remove_at(i)
	_selected_index = min(i, s.order.size() - 1)
	_render(s)

func _move_up() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	if s.order.size() < 2 or _selected_index <= 0:
		return
	var i: int = _selected_index
	var a: String = s.order[i - 1]
	s.order[i - 1] = s.order[i]
	s.order[i] = a
	_selected_index -= 1
	_render(s)

func _move_down() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	if s.order.size() < 2 or _selected_index < 0 or _selected_index >= s.order.size() - 1:
		return
	var i: int = _selected_index
	var a: String = s.order[i + 1]
	s.order[i + 1] = s.order[i]
	s.order[i] = a
	_selected_index += 1
	_render(s)

func _start() -> void:
	GameController.play_ui_click()
	var s: Model.GameState = GameController.state
	s.rules.bank_initial_ms = int(bank.value) * 1000
	s.rules.cooldown_ms = int(cd.value) * 1000
	s.rules.warn_every_ms = int(warn.value) * 1000

	for player_name in s.players.keys():
		s.bank_ms[player_name] = s.rules.bank_initial_ms

	err.text = ""
	GameController.dispatch({"type": Const.CMD_START_GAME})
