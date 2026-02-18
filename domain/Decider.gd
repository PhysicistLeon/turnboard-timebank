extends RefCounted
class_name Decider

static func decide(state: Model.GameState, cmd: Dictionary, now_mono_ms: int, ctx: Dictionary) -> Dictionary:
	var out := {
		"ok": true,
		"error": "",
		"events": [] as Array[Dictionary]
	}

	var type: String = cmd.get("type", "")
	match type:
		Const.CMD_TICK:
			if state.phase != Const.Phase.RUNNING:
				return out
			_emit_time_based_events(state, now_mono_ms, out["events"])

		Const.CMD_START_GAME:
			if state.phase != Const.Phase.SETUP:
				return _err(out, "Not in SETUP")
			if state.order.is_empty():
				return _err(out, "Order is empty")
			if state.players.size() != state.order.size():
				return _err(out, "Players/order mismatch")
			if state.rules.warn_every_ms <= 0:
				return _err(out, "warn_every must be > 0")

			var gid := cmd.get("game_id", "")
			if gid == "":
				gid = str(Time.get_unix_time_from_system())

			out["events"].append({
				"type": Const.EV_GAME_START,
				"game_id": gid,
				"order": state.order,
				"order_dir": state.order_dir
			})

			var first := state.order[0]
			out["events"].append({
				"type": Const.EV_TURN_START,
				"player": first,
				"at_mono_ms": now_mono_ms
			})
			out["events"].append({
				"type": Const.EV_COOLDOWN_START,
				"player": first,
				"at_mono_ms": now_mono_ms
			})

		Const.CMD_TAP:
			if state.phase != Const.Phase.RUNNING:
				return _err(out, "Not RUNNING")

			var pre_events: Array[Dictionary] = []
			_emit_time_based_events(state, now_mono_ms, pre_events)

			var projected := state.clone()
			for ev in pre_events:
				projected = Reducer.apply(projected, ev)

			for ev in pre_events:
				out["events"].append(ev)

			var player := projected.current
			var bank_after := projected.derive_current_bank_ms(now_mono_ms)
			var spent_no_cd := projected.derive_elapsed_no_cooldown_ms(now_mono_ms)
			var warn_count := projected.warn_emitted_count

			out["events"].append({
				"type": Const.EV_TURN_END,
				"player": player,
				"bank_after_ms": bank_after,
				"spent_no_cooldown_ms": spent_no_cd,
				"warn_emitted_count": warn_count,
				"at_mono_ms": now_mono_ms
			})

			var next := Util.compute_next(projected.order, projected.order_dir, player)
			out["events"].append({
				"type": Const.EV_TURN_START,
				"player": next,
				"at_mono_ms": now_mono_ms
			})
			out["events"].append({
				"type": Const.EV_COOLDOWN_START,
				"player": next,
				"at_mono_ms": now_mono_ms
			})

		Const.CMD_TECH_PAUSE_ON:
			if state.phase != Const.Phase.RUNNING:
				return out
			var reason := String(cmd.get("reason", "manual"))
			_emit_time_based_events(state, now_mono_ms, out["events"])
			out["events"].append({
				"type": Const.EV_TECH_PAUSE_ON,
				"at_mono_ms": now_mono_ms,
				"reason": reason
			})

		Const.CMD_TECH_PAUSE_OFF:
			if state.phase != Const.Phase.TECH_PAUSE:
				return out
			out["events"].append({
				"type": Const.EV_TECH_PAUSE_OFF,
				"at_mono_ms": now_mono_ms
			})

		Const.CMD_NEW_GAME:
			if state.phase != Const.Phase.TECH_PAUSE and state.phase != Const.Phase.SETUP:
				return _err(out, "New game allowed only from SETUP/TECH_PAUSE")
			var gid2 := str(Time.get_unix_time_from_system())
			out["events"].append({
				"type": Const.EV_NEW_GAME,
				"game_id": gid2,
				"at_mono_ms": now_mono_ms
			})

		Const.CMD_ADMIN_AUTH:
			if state.phase != Const.Phase.TECH_PAUSE:
				return _err(out, "Admin auth allowed only in TECH_PAUSE")
			var pass := String(cmd.get("password", ""))
			var real := String(ctx.get("admin_password", ""))
			if pass == "" or real == "":
				return _err(out, "Password not configured")
			if pass == real:
				out["events"].append({"type": Const.EV_ADMIN_AUTH_OK})
				out["events"].append({"type": Const.EV_ADMIN_MODE_ON})
			else:
				out["events"].append({"type": Const.EV_ADMIN_AUTH_FAIL})

		Const.CMD_ADMIN_EDIT:
			if state.started:
				if state.phase != Const.Phase.TECH_PAUSE or not state.admin_mode:
					return _err(out, "Admin edit requires admin_mode in TECH_PAUSE")
				out["events"].append({
					"type": Const.EV_ADMIN_EDIT,
					"edit_type": cmd.get("edit_type", ""),
					"payload": cmd.get("payload", {}),
					"old": cmd.get("old", {}),
					"new": cmd.get("new", {})
				})
			else:
				out["events"].append({
					"type": Const.EV_ADMIN_EDIT,
					"edit_type": cmd.get("edit_type", ""),
					"payload": cmd.get("payload", {}),
					"old": cmd.get("old", {}),
					"new": cmd.get("new", {})
				})

		Const.CMD_UNDO:
			if state.phase != Const.Phase.TECH_PAUSE or not state.admin_mode:
				return _err(out, "Undo requires admin_mode in TECH_PAUSE")
			out["events"].append({
				"type": Const.EV_TURN_UNDO,
				"at_mono_ms": now_mono_ms
			})

		Const.CMD_ORDER_REVERSE:
			if state.phase != Const.Phase.TECH_PAUSE or not state.admin_mode:
				return _err(out, "Reverse requires admin_mode in TECH_PAUSE")
			var old_dir := state.order_dir
			var new_dir := Const.OrderDir.CCW if old_dir == Const.OrderDir.CW else Const.OrderDir.CW
			out["events"].append({
				"type": Const.EV_ORDER_REVERSE,
				"old_dir": old_dir,
				"new_dir": new_dir
			})

		Const.CMD_APP_PAUSED:
			out["events"].append({"type": Const.EV_APP_BACKGROUND})
			if state.phase == Const.Phase.RUNNING:
				_emit_time_based_events(state, now_mono_ms, out["events"])
				out["events"].append({
					"type": Const.EV_TECH_PAUSE_ON,
					"at_mono_ms": now_mono_ms,
					"reason": "app_paused"
				})

		Const.CMD_APP_RESUMED:
			out["events"].append({"type": Const.EV_APP_RESUME})

		_:
			pass

	return out

static func _emit_time_based_events(state: Model.GameState, now_mono_ms: int, events: Array[Dictionary]) -> void:
	if state.subphase == Const.Subphase.COOLDOWN and now_mono_ms >= state.cooldown_end_mono_ms and state.cooldown_end_mono_ms > 0:
		events.append({
			"type": Const.EV_COOLDOWN_END,
			"at_mono_ms": state.cooldown_end_mono_ms
		})

	if state.subphase == Const.Subphase.COUNTDOWN:
		var elapsed := state.derive_elapsed_no_cooldown_ms(now_mono_ms)
		var w := state.rules.warn_every_ms
		if w > 0:
			var target_count := int(floor(float(elapsed) / float(w)))
			for i in range(state.warn_emitted_count + 1, target_count + 1):
				events.append({
					"type": Const.EV_WARN_LONG_TURN,
					"count": i,
					"at_elapsed_ms": i * w
				})

static func _err(out: Dictionary, msg: String) -> Dictionary:
	out["ok"] = false
	out["error"] = msg
	return out
