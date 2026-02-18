extends RefCounted
class_name Util

static func ms_to_mmss(ms: int) -> String:
	var prefix := ""
	var v := ms
	if v < 0:
		prefix = "-"
		v = -v
	var total_sec := int(floor(v / 1000.0))
	var mm: int = int(total_sec / 60.0)
	var ss := total_sec % 60
	return "%s%02d:%02d" % [prefix, mm, ss]

static func compute_next(order: PackedStringArray, dir: int, current: String) -> String:
	if order.is_empty():
		return ""
	var idx := order.find(current)
	if idx == -1:
		return order[0]
	if dir == Const.OrderDir.CW:
		return order[(idx + 1) % order.size()]
	else:
		return order[(idx - 1 + order.size()) % order.size()]

static func safe_join_order(order: PackedStringArray) -> String:
	return ",".join(order)

static func clamp01(x: float) -> float:
	return min(1.0, max(0.0, x))

static func blink_hz(bank_ms: int, bank_initial_ms: int, min_hz: float, max_hz: float) -> float:
	if bank_initial_ms <= 0:
		return max_hz
	var prog := clamp01(float(bank_ms) / float(bank_initial_ms))
	var t := 1.0 - prog
	return lerpf(min_hz, max_hz, t)
