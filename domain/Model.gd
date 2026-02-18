extends RefCounted
class_name Model

class Player:
	extends RefCounted
	var name: String = ""
	var color: Color = Color.WHITE
	var sound_tap: String = ""
	var sound_warn: String = ""

	func clone() -> Player:
		var p := Player.new()
		p.name = name
		p.color = color
		p.sound_tap = sound_tap
		p.sound_warn = sound_warn
		return p

class Rules:
	extends RefCounted
	var bank_initial_ms: int = 5 * 60 * 1000
	var cooldown_ms: int = 5 * 1000
	var warn_every_ms: int = 60 * 1000
	var warn_sound: String = ""

	func clone() -> Rules:
		var r := Rules.new()
		r.bank_initial_ms = bank_initial_ms
		r.cooldown_ms = cooldown_ms
		r.warn_every_ms = warn_every_ms
		r.warn_sound = warn_sound
		return r

class TurnRecord:
	extends RefCounted
	var player_name: String = ""
	var bank_after_ms: int = 0
	var spent_no_cooldown_ms: int = 0
	var warn_emitted_count: int = 0

class GameState:
	extends RefCounted

	var phase: int = Const.Phase.SETUP
	var started: bool = false
	var game_id: String = ""

	var rules: Rules = Rules.new()
	var players: Dictionary = {}
	var order: PackedStringArray = []
	var order_dir: int = Const.OrderDir.CW
	var bank_ms: Dictionary = {}

	var current: String = ""
	var subphase: int = Const.Subphase.NONE

	var cooldown_end_mono_ms: int = 0
	var countdown_start_mono_ms: int = 0
	var current_bank_base_ms: int = 0

	var elapsed_no_cooldown_base_ms: int = 0
	var warn_emitted_count: int = 0

	var pause_mono_ms: int = 0
	var pause_reason: String = ""

	var admin_mode: bool = false

	var turn_history: Array[TurnRecord] = []

	func clone() -> GameState:
		var s := GameState.new()
		s.phase = phase
		s.started = started
		s.game_id = game_id
		s.rules = rules.clone()

		s.players = {}
		for k in players.keys():
			s.players[k] = (players[k] as Player).clone()

		s.order = order.duplicate()
		s.order_dir = order_dir
		s.bank_ms = bank_ms.duplicate(true)

		s.current = current
		s.subphase = subphase
		s.cooldown_end_mono_ms = cooldown_end_mono_ms
		s.countdown_start_mono_ms = countdown_start_mono_ms
		s.current_bank_base_ms = current_bank_base_ms
		s.elapsed_no_cooldown_base_ms = elapsed_no_cooldown_base_ms
		s.warn_emitted_count = warn_emitted_count
		s.pause_mono_ms = pause_mono_ms
		s.pause_reason = pause_reason
		s.admin_mode = admin_mode

		s.turn_history = []
		for rec in turn_history:
			var r := TurnRecord.new()
			r.player_name = rec.player_name
			r.bank_after_ms = rec.bank_after_ms
			r.spent_no_cooldown_ms = rec.spent_no_cooldown_ms
			r.warn_emitted_count = rec.warn_emitted_count
			s.turn_history.append(r)

		return s

	func effective_now_mono(now_mono_ms: int) -> int:
		return pause_mono_ms if phase == Const.Phase.TECH_PAUSE and pause_mono_ms > 0 else now_mono_ms

	func derive_current_bank_ms(now_mono_ms: int) -> int:
		if current == "":
			return 0
		var eff: int = effective_now_mono(now_mono_ms)
		if phase == Const.Phase.RUNNING and subphase == Const.Subphase.COUNTDOWN:
			var spent: int = int(max(0, eff - countdown_start_mono_ms))
			return current_bank_base_ms - spent
		return current_bank_base_ms

	func derive_elapsed_no_cooldown_ms(now_mono_ms: int) -> int:
		var eff: int = effective_now_mono(now_mono_ms)
		if phase == Const.Phase.RUNNING and subphase == Const.Subphase.COUNTDOWN:
			return elapsed_no_cooldown_base_ms + int(max(0, eff - countdown_start_mono_ms))
		return elapsed_no_cooldown_base_ms

	func cooldown_remaining_ms(now_mono_ms: int) -> int:
		if phase != Const.Phase.RUNNING or subphase != Const.Subphase.COOLDOWN:
			return 0
		var eff: int = effective_now_mono(now_mono_ms)
		return max(0, cooldown_end_mono_ms - eff)
