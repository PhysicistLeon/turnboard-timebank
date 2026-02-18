extends RefCounted
class_name Reducer

static func apply(s: Model.GameState, ev: Dictionary) -> Model.GameState:
	var t: String = ev.get("type", "")
	match t:
		Const.EV_GAME_START:
			s.started = true
			s.phase = Const.Phase.RUNNING
			s.game_id = ev["game_id"]
			s.order = ev["order"]
			s.order_dir = ev["order_dir"]
		Const.EV_NEW_GAME:
			s.game_id = ev["game_id"]
			for name in s.players.keys():
				s.bank_ms[name] = s.rules.bank_initial_ms
			s.phase = Const.Phase.RUNNING
			s.admin_mode = false
			s.turn_history.clear()
			if not s.order.is_empty():
				s.current = s.order[0]
				s.subphase = Const.Subphase.COOLDOWN
				s.cooldown_end_mono_ms = ev["at_mono_ms"] + s.rules.cooldown_ms
				s.countdown_start_mono_ms = 0
				s.current_bank_base_ms = int(s.bank_ms[s.current])
				s.elapsed_no_cooldown_base_ms = 0
				s.warn_emitted_count = 0

		Const.EV_TURN_START:
			s.current = ev["player"]
			s.subphase = Const.Subphase.COOLDOWN
			s.cooldown_end_mono_ms = ev["at_mono_ms"] + s.rules.cooldown_ms
			s.countdown_start_mono_ms = 0
			s.current_bank_base_ms = int(s.bank_ms.get(s.current, s.rules.bank_initial_ms))
			s.elapsed_no_cooldown_base_ms = 0
			s.warn_emitted_count = 0

		Const.EV_COOLDOWN_END:
			s.subphase = Const.Subphase.COUNTDOWN
			s.countdown_start_mono_ms = ev["at_mono_ms"]
			s.elapsed_no_cooldown_base_ms = 0
			s.warn_emitted_count = 0

		Const.EV_WARN_LONG_TURN:
			s.warn_emitted_count = max(s.warn_emitted_count, int(ev.get("count", s.warn_emitted_count)))

		Const.EV_TURN_END:
			var rec := Model.TurnRecord.new()
			rec.player_name = ev["player"]
			rec.bank_after_ms = ev["bank_after_ms"]
			rec.spent_no_cooldown_ms = ev["spent_no_cooldown_ms"]
			rec.warn_emitted_count = int(ev.get("warn_emitted_count", 0))
			s.turn_history.append(rec)
			s.bank_ms[rec.player_name] = rec.bank_after_ms

		Const.EV_TECH_PAUSE_ON:
			s.phase = Const.Phase.TECH_PAUSE
			s.pause_mono_ms = ev["at_mono_ms"]
			s.pause_reason = ev.get("reason", "")

		Const.EV_TECH_PAUSE_OFF:
			var at := int(ev["at_mono_ms"])
			if s.pause_mono_ms > 0:
				var delta := at - s.pause_mono_ms
				if delta > 0:
					if s.subphase == Const.Subphase.COOLDOWN:
						s.cooldown_end_mono_ms += delta
					elif s.subphase == Const.Subphase.COUNTDOWN:
						s.countdown_start_mono_ms += delta
				s.pause_mono_ms = 0
				s.pause_reason = ""
			s.phase = Const.Phase.RUNNING
			s.admin_mode = false

		Const.EV_ADMIN_MODE_ON:
			s.admin_mode = true
		Const.EV_ADMIN_MODE_OFF:
			s.admin_mode = false

		Const.EV_ORDER_REVERSE:
			s.order_dir = int(ev["new_dir"])

		Const.EV_TURN_UNDO:
			if s.turn_history.is_empty():
				return s
			var last: Model.TurnRecord = s.turn_history.pop_back()
			s.current = last.player_name
			s.subphase = Const.Subphase.COUNTDOWN
			s.current_bank_base_ms = last.bank_after_ms
			s.elapsed_no_cooldown_base_ms = last.spent_no_cooldown_ms
			s.warn_emitted_count = last.warn_emitted_count
			s.countdown_start_mono_ms = int(ev["at_mono_ms"])
			s.bank_ms[s.current] = last.bank_after_ms

		Const.EV_ADMIN_EDIT:
			var et: String = String(ev.get("edit_type", ""))
			var p: Dictionary = ev.get("payload", {})
			match et:
				"set_bank":
					var name := String(p["name"])
					s.bank_ms[name] = int(p["bank_ms"])
					if name == s.current:
						s.current_bank_base_ms = int(s.bank_ms[name])
				"reorder":
					s.order = p["new_order"]
				"rename":
					_apply_rename(s, String(p["old_name"]), String(p["new_name"]))
				"set_rules":
					s.rules.bank_initial_ms = int(p["bank_initial_ms"])
					s.rules.cooldown_ms = int(p["cooldown_ms"])
					s.rules.warn_every_ms = int(p["warn_every_ms"])
				_:
					pass

		Const.EV_ERROR:
			pass
		_:
			pass

	return s

static func _apply_rename(s: Model.GameState, old_name: String, new_name: String) -> void:
	if old_name == new_name:
		return
	if not s.players.has(old_name):
		return
	if s.players.has(new_name):
		return

	var pl: Model.Player = s.players[old_name]
	s.players.erase(old_name)
	pl.name = new_name
	s.players[new_name] = pl

	var b := int(s.bank_ms.get(old_name, s.rules.bank_initial_ms))
	s.bank_ms.erase(old_name)
	s.bank_ms[new_name] = b

	for i in range(s.order.size()):
		if s.order[i] == old_name:
			s.order[i] = new_name

	if s.current == old_name:
		s.current = new_name

	for rec in s.turn_history:
		if rec.player_name == old_name:
			rec.player_name = new_name
