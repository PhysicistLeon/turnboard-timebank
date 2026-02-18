extends Control

@onready var state_line := $VBox/StateLine
@onready var list := $VBox/PlayersList

@onready var admin_pass := $VBox/AdminBox/AdminPass
@onready var admin_status := $VBox/AdminBox/AdminStatus

func _ready() -> void:
	GameController.state_changed.connect(_render)

	$VBox/ContinueBtn.pressed.connect(_continue)
	$VBox/NewGameBtn.pressed.connect(_new_game)
	$VBox/AdminBox/AdminBtn.pressed.connect(_admin_auth)
	$VBox/AdminActions/UndoBtn.pressed.connect(_undo)
	$VBox/AdminActions/ReverseBtn.pressed.connect(_reverse)

	admin_pass.secret = false
	admin_pass.text_submitted.connect(_on_admin_pass_submitted)
	_render(GameController.state)

func _render(s: Model.GameState) -> void:
	var now: int = Time.get_ticks_msec()
	state_line.text = "current=%s phase=%s sub=%s cd_rem=%sms admin=%s" % [
		s.current,
		Const.Phase.keys()[s.phase],
		Const.Subphase.keys()[s.subphase],
		s.cooldown_remaining_ms(now),
		str(s.admin_mode)
	]

	list.clear()
	for player_name in s.order:
		var b: int = int(s.bank_ms.get(player_name, s.rules.bank_initial_ms))
		list.add_item("%s   %s" % [player_name, Util.ms_to_mmss(b)])

	$VBox/AdminActions.visible = s.admin_mode

func _continue() -> void:
	GameController.play_ui_click()
	GameController.dispatch({"type": Const.CMD_TECH_PAUSE_OFF})

func _new_game() -> void:
	GameController.play_ui_click()
	GameController.dispatch({"type": Const.CMD_NEW_GAME})

func _admin_auth() -> void:
	GameController.play_ui_click()
	var entered_password: String = admin_pass.text
	if entered_password.strip_edges() == "":
		admin_status.text = "Введите пароль"
		return

	GameController.dispatch({"type": Const.CMD_ADMIN_AUTH, "password": entered_password})

	if GameController.state.admin_mode:
		admin_status.text = "Доступ разрешён"
	else:
		admin_status.text = "Неверный пароль"

func _on_admin_pass_submitted(_text: String) -> void:
	_admin_auth()

func _undo() -> void:
	GameController.play_ui_click()
	GameController.dispatch({"type": Const.CMD_UNDO})

func _reverse() -> void:
	GameController.play_ui_click()
	GameController.dispatch({"type": Const.CMD_ORDER_REVERSE})
