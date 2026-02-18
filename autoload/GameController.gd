extends Node

signal state_changed(state: Model.GameState)
signal route_changed(route: String)

const StorageScript := preload("res://infra/Storage.gd")
const LoggerScript := preload("res://infra/Logger.gd")
const SoundServiceScript := preload("res://infra/SoundService.gd")

var storage = StorageScript.new()
var event_logger = LoggerScript.new()
var sound = SoundServiceScript.new()

var state := Model.GameState.new()
var seq: int = 1

var _tick_accum := 0.0
const TICK_PERIOD := 0.10

func _ready() -> void:
	add_child(sound)

	storage.load_cfg()
	seq = storage.get_log_seq()

	if state.players.is_empty():
		_seed_default_players()

	if not storage.has_password():
		route_changed.emit("password")
	else:
		route_changed.emit("setup")

	dispatch({"type": Const.EV_APP_START}, true)

func _process(delta: float) -> void:
	_tick_accum += delta
	if _tick_accum >= TICK_PERIOD:
		_tick_accum = 0.0
		dispatch({"type": Const.CMD_TICK})

func _notification(what: int) -> void:
	if what == MainLoop.NOTIFICATION_APPLICATION_PAUSED:
		dispatch({"type": Const.CMD_APP_PAUSED})
	elif what == MainLoop.NOTIFICATION_APPLICATION_RESUMED:
		dispatch({"type": Const.CMD_APP_RESUMED})

func now_mono_ms() -> int:
	return Time.get_ticks_msec()

func now_wall_iso() -> String:
	return Time.get_datetime_string_from_system(true, true)

func dispatch(cmd: Dictionary, is_internal_event := false) -> void:
	var now: int = now_mono_ms()

	if is_internal_event:
		_apply_and_log_if_needed(cmd, false)
		state_changed.emit(state)
		return

	var ctx: Dictionary = {"admin_password": storage.get_password()}
	var result: Dictionary = Decider.decide(state, cmd, now, ctx)
	if not bool(result["ok"]):
		return

	if cmd.get("type", "") == Const.CMD_TAP and state.phase == Const.Phase.RUNNING:
		_play_tap_for_current()
		Input.vibrate_handheld(60, -1.0)

	for ev in result["events"]:
		_apply_and_log_if_needed(ev, true)

	_apply_platform_effects()
	state_changed.emit(state)

func _apply_and_log_if_needed(ev: Dictionary, write_log: bool) -> void:
	if write_log:
		var line: String = _format_log_line(ev)
		var ok: bool = event_logger.append_line(line)
		if not ok:
			pass
		seq += 1
		storage.set_log_seq(seq)
		storage.save_cfg()

	state = Reducer.apply(state, ev)

func _format_log_line(ev: Dictionary) -> String:
	var ts: String = now_wall_iso()
	var gid: String = state.game_id if state.game_id != "" else "-"
	var t := String(ev.get("type", ""))
	var parts: Array[String] = []
	for k in ev.keys():
		if k == "type":
			continue
		var v: Variant = ev[k]
		var sv := str(v)
		if sv.find(" ") != -1 or sv.find(",") != -1:
			sv = "\"" + sv + "\""
		parts.append("%s=%s" % [k, sv])
	parts.sort()
	var kv := " ".join(parts)
	return "%s %d G=%s %s %s" % [ts, seq, gid, t, kv]

func _apply_platform_effects() -> void:
	if state.phase == Const.Phase.RUNNING:
		DisplayServer.screen_set_keep_on(true)
		route_changed.emit("game")
	elif state.phase == Const.Phase.TECH_PAUSE:
		DisplayServer.screen_set_keep_on(false)
		route_changed.emit("pause")
	else:
		DisplayServer.screen_set_keep_on(false)
		route_changed.emit("setup")

func _play_tap_for_current() -> void:
	var player_name: String = state.current
	if player_name == "" or not state.players.has(player_name):
		return
	var p: Model.Player = state.players[player_name]
	if p.sound_tap == "":
		return
	var stream := sound.load_audio_from_path(p.sound_tap)
	if stream != null:
		sound.play_stream(stream)

func _seed_default_players() -> void:
	var a := Model.Player.new()
	a.name = "A"
	a.color = Color(0.9, 0.2, 0.2)
	var b := Model.Player.new()
	b.name = "B"
	b.color = Color(0.2, 0.6, 0.9)

	state.players[a.name] = a
	state.players[b.name] = b
	state.order = PackedStringArray([a.name, b.name])
	state.bank_ms[a.name] = state.rules.bank_initial_ms
	state.bank_ms[b.name] = state.rules.bank_initial_ms
