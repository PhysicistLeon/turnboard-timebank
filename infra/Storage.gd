extends RefCounted
class_name Storage

var cfg_path: String = "user://config.ini"
var cfg: ConfigFile = ConfigFile.new()

func load_cfg() -> void:
	cfg.load(cfg_path)

func save_cfg() -> void:
	cfg.save(cfg_path)

func has_password() -> bool:
	return String(cfg.get_value("admin", "password", "")) != ""

func get_password() -> String:
	return String(cfg.get_value("admin", "password", ""))

func set_password(p: String) -> void:
	cfg.set_value("admin", "password", p)

func get_log_seq() -> int:
	return int(cfg.get_value("log", "seq", 1))

func set_log_seq(v: int) -> void:
	cfg.set_value("log", "seq", v)
