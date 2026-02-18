extends RefCounted
class_name Logger

var path: String = "user://logs/events.log"

func ensure_dir() -> void:
	if not DirAccess.dir_exists_absolute("user://logs"):
		DirAccess.make_dir_recursive_absolute("user://logs")

func append_line(line: String) -> bool:
	ensure_dir()
	var f: FileAccess = FileAccess.open(path, FileAccess.READ_WRITE)
	if f == null:
		return false
	f.seek_end()
	f.store_line(line)
	f.flush()
	return true
