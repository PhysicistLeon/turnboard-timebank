extends Node
class_name SoundService

const LIBRARY_DIR := "user://sounds"

@onready var player: AudioStreamPlayer = AudioStreamPlayer.new()
var _mp3_paths: Array[String] = []

func _ready() -> void:
	add_child(player)
	_ensure_library_dir()
	refresh_library()

func play_stream(stream: AudioStream) -> void:
	if stream == null:
		return
	player.stop()
	player.stream = stream
	player.play()

func play_random_from_library(fallback_path: String) -> void:
	if _mp3_paths.is_empty():
		play_stream(load(fallback_path) as AudioStream)
		return

	var path := _mp3_paths.pick_random()
	var stream := load_audio_from_path(path)
	if stream == null:
		play_stream(load(fallback_path) as AudioStream)
		return
	play_stream(stream)

func refresh_library() -> void:
	_mp3_paths.clear()
	for f in DirAccess.get_files_at(LIBRARY_DIR):
		if f.get_extension().to_lower() == "mp3":
			_mp3_paths.append(LIBRARY_DIR.path_join(f))

func import_mp3_folder(folder_path_or_uri: String) -> Dictionary:
	_ensure_library_dir()
	var imported := 0
	var failed := 0

	for source_path in _collect_mp3_sources(folder_path_or_uri):
		var bytes := FileAccess.get_file_as_bytes(source_path)
		if bytes.is_empty():
			failed += 1
			continue

		var file_name := source_path.get_file()
		if file_name.is_empty() or file_name.get_extension().to_lower() != "mp3":
			file_name = "sound_%s.mp3" % str(Time.get_ticks_usec())

		var dst := _make_unique_dst_path(file_name)
		var out := FileAccess.open(dst, FileAccess.WRITE)
		if out == null:
			failed += 1
			continue
		out.store_buffer(bytes)
		imported += 1

	refresh_library()
	return {
		"imported": imported,
		"failed": failed,
		"total": imported + failed,
		"library_count": _mp3_paths.size()
	}

func _ensure_library_dir() -> void:
	DirAccess.make_dir_recursive_absolute(LIBRARY_DIR)

func _collect_mp3_sources(folder_path_or_uri: String) -> Array[String]:
	var result: Array[String] = []
	for file_name in DirAccess.get_files_at(folder_path_or_uri):
		if file_name.get_extension().to_lower() != "mp3":
			continue
		var src := folder_path_or_uri.path_join(file_name)
		result.append(src)
	return result

func _make_unique_dst_path(file_name: String) -> String:
	var dot := file_name.rfind(".")
	var base := file_name
	var ext := ""
	if dot > 0:
		base = file_name.substr(0, dot)
		ext = file_name.substr(dot)

	var candidate := LIBRARY_DIR.path_join(file_name)
	var index := 1
	while FileAccess.file_exists(candidate):
		candidate = LIBRARY_DIR.path_join("%s_%d%s" % [base, index, ext])
		index += 1
	return candidate

func load_audio_from_path(path_or_uri: String) -> AudioStream:
	var lower: String = path_or_uri.to_lower()
	if lower.ends_with(".mp3"):
		var bytes := FileAccess.get_file_as_bytes(path_or_uri)
		if bytes.is_empty():
			return null
		var s := AudioStreamMP3.new()
		s.data = bytes
		return s
	if lower.ends_with(".ogg"):
		var s2: AudioStreamOggVorbis = AudioStreamOggVorbis.load_from_file(path_or_uri)
		return s2
	if lower.ends_with(".wav"):
		var s3: AudioStreamWAV = AudioStreamWAV.load_from_file(path_or_uri)
		return s3
	return null
