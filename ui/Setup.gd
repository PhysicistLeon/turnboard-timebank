extends Control

@onready var list := $VBox/PlayersList
@onready var err := $VBox/Error

@onready var bank := $VBox/GridRules/BankMs
@onready var cd := $VBox/GridRules/CooldownMs
@onready var warn := $VBox/GridRules/WarnEveryMs

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
	list.clear()
	for name in s.order:
		var bms := int(s.bank_ms.get(name, s.rules.bank_initial_ms))
		list.add_item("%s   %s" % [name, Util.ms_to_mmss(bms)])

	bank.value = int(round(s.rules.bank_initial_ms / 1000.0))
	cd.value = int(round(s.rules.cooldown_ms / 1000.0))
	warn.value = int(round(s.rules.warn_every_ms / 1000.0))

func _add_player() -> void:
	var s: Model.GameState = GameController.state
	var base := "P"
	var i := 1
	var name := "%s%d" % [base, i]
	while s.players.has(name):
		i += 1
		name = "%s%d" % [base, i]
	var p := Model.Player.new()
	p.name = name
	p.color = Color.WHITE
	s.players[name] = p
	s.order.append(name)
	s.bank_ms[name] = s.rules.bank_initial_ms
	_render(s)

func _remove_player() -> void:
	var idx: PackedInt32Array = list.get_selected_items()
	if idx.is_empty():
		return
	var i: int = idx[0]
	var name: String = GameController.state.order[i]
	GameController.state.players.erase(name)
	GameController.state.bank_ms.erase(name)
	GameController.state.order.remove_at(i)
	_render(GameController.state)

func _move_up() -> void:
	var idx: PackedInt32Array = list.get_selected_items()
	if idx.is_empty():
		return
	var i: int = idx[0]
	if i <= 0:
		return
	var s: Model.GameState = GameController.state
	var a: String = s.order[i - 1]
	s.order[i - 1] = s.order[i]
	s.order[i] = a
	_render(s)
	list.select(i - 1)

func _move_down() -> void:
	var idx: PackedInt32Array = list.get_selected_items()
	if idx.is_empty():
		return
	var i: int = idx[0]
	var s: Model.GameState = GameController.state
	if i >= s.order.size() - 1:
		return
	var a: String = s.order[i + 1]
	s.order[i + 1] = s.order[i]
	s.order[i] = a
	_render(s)
	list.select(i + 1)

func _start() -> void:
	var s: Model.GameState = GameController.state
	s.rules.bank_initial_ms = int(bank.value) * 1000
	s.rules.cooldown_ms = int(cd.value) * 1000
	s.rules.warn_every_ms = int(warn.value) * 1000

	for name in s.players.keys():
		s.bank_ms[name] = s.rules.bank_initial_ms

	err.text = ""
	GameController.dispatch({"type": Const.CMD_START_GAME})
