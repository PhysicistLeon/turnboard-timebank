extends Control

@onready var bg := $Bg
@onready var big := $BigBtn
@onready var name_lbl := $BigBtn/VBox/Name
@onready var time_lbl := $BigBtn/VBox/Time
@onready var pause_btn := $PauseBtn

var _t0 := 0.0

func _ready() -> void:
	GameController.state_changed.connect(_render_static)
	big.pressed.connect(_tap)
	pause_btn.pressed.connect(_pause)
	_render_static(GameController.state)

func _process(delta: float) -> void:
	var s: Model.GameState = GameController.state
	if s.phase != Const.Phase.RUNNING:
		return

	var now: int = Time.get_ticks_msec()
	var bank_ms: int = s.derive_current_bank_ms(now)
	time_lbl.text = Util.ms_to_mmss(bank_ms)

	var col: Color = Color.BLACK
	if s.players.has(s.current):
		col = (s.players[s.current] as Model.Player).color

	var hz: float = Util.blink_hz(bank_ms, s.rules.bank_initial_ms, 1.0 / 60.0, 1.0)
	_t0 += delta
	var x: float = fposmod(_t0 * hz, 1.0)
	var wave: float = (x * 2.0) if x < 0.5 else ((1.0 - x) * 2.0)
	bg.color = Color.BLACK.lerp(col, wave)

func _render_static(s: Model.GameState) -> void:
	var now: int = Time.get_ticks_msec()
	name_lbl.text = s.current
	time_lbl.text = Util.ms_to_mmss(s.derive_current_bank_ms(now))

func _tap() -> void:
	GameController.dispatch({"type": Const.CMD_TAP})

func _pause() -> void:
	GameController.dispatch({"type": Const.CMD_TECH_PAUSE_ON, "reason": "manual"})
