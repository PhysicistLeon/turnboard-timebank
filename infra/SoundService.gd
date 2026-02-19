extends Node
class_name SoundService

const LIBRARY_DIR := "user://sounds"
const DEFAULT_UI_CLICK_PATH := "res://sounds/kriakalka.mp3"

@onready var player: AudioStreamPlayer = AudioStreamPlayer.new()

var _library_mp3_paths: Array[String] = []
var _default_click_stream: AudioStream = null

func _ready() -> void:
	add_child(player)
	DirAccess.make_dir_recursive_absolute(LIBRARY_DIR)
	_default_click_stream = load(DEFAULT_UI_CLICK_PATH) as AudioStream
	refresh_library()

func play_stream(stream: AudioStream) -> void:
	if stream == null:
		return
	player.stop()
	player.stream = stream
	player.play()

func load_audio_from_path(path_or_uri: String) -> AudioStream:
	var lower: String = path_or_uri.to_lower()
	if lower.ends_with(".mp3"):
		var s: AudioStreamMP3 = AudioStreamMP3.load_from_file(path_or_uri)
		return s
	if lower.ends_with(".ogg"):
		var s2: AudioStreamOggVorbis = AudioStreamOggVorbis.load_from_file(path_or_uri)
		return s2
	if lower.ends_with(".wav"):
		var s3: AudioStreamWAV = AudioStreamWAV.load_from_file(path_or_uri)
		return s3
	return null

func refresh_library() -> void:
	_library_mp3_paths.clear()
	var dir := DirAccess.open(LIBRARY_DIR)
	if dir == null:
		return
	dir.list_dir_begin()
	while true:
		var name := dir.get_next()
		if name == "":
			break
		if dir.current_is_dir():
			continue
		if name.get_extension().to_lower() == "mp3":
			_library_mp3_paths.append(LIBRARY_DIR.path_join(name))
	dir.list_dir_end()

func play_random_library_click() -> void:
	if _library_mp3_paths.is_empty():
		if _default_click_stream != null:
			play_stream(_default_click_stream)
		return

	var path := _library_mp3_paths.pick_random()
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.is_empty():
		if _default_click_stream != null:
			play_stream(_default_click_stream)
		return

	var stream := AudioStreamMP3.new()
	stream.data = bytes
	play_stream(stream)

func import_mp3_directory_via_picker(on_done: Callable = Callable()) -> void:
	if not DisplayServer.has_feature(DisplayServer.FEATURE_NATIVE_DIALOG_FILE):
		if on_done.is_valid():
			on_done.call("Native file dialog is not supported", 0)
		return

	DisplayServer.file_dialog_show(
		"Импорт папки со звуками",
		"",
		"",
		false,
		DisplayServer.FILE_DIALOG_MODE_OPEN_DIR,
		PackedStringArray(["*.mp3;MP3 Audio;audio/mpeg"]),
		func(ok: bool, selected: PackedStringArray, _filter_idx: int) -> void:
			if not ok or selected.is_empty():
				if on_done.is_valid():
					on_done.call("Импорт отменён", 0)
				return
			var imported := import_mp3_from_directory(selected[0])
			if on_done.is_valid():
				on_done.call("Импортировано mp3: %d" % imported, imported)
	)

func import_mp3_from_directory(source_dir: String) -> int:
	DirAccess.make_dir_recursive_absolute(LIBRARY_DIR)
	var imported := 0
	var dir := DirAccess.open(source_dir)
	if dir == null:
		return 0

	dir.list_dir_begin()
	while true:
		var file_name := dir.get_next()
		if file_name == "":
			break
		if dir.current_is_dir():
			continue
		if file_name.get_extension().to_lower() != "mp3":
			continue

		var src_path := source_dir.path_join(file_name)
		var bytes := FileAccess.get_file_as_bytes(src_path)
		if bytes.is_empty():
			continue

		var target_name := _build_unique_library_name(file_name)
		var dst_path := LIBRARY_DIR.path_join(target_name)
		var out := FileAccess.open(dst_path, FileAccess.WRITE)
		if out == null:
			continue
		out.store_buffer(bytes)
		imported += 1
	dir.list_dir_end()

	refresh_library()
	return imported

func _build_unique_library_name(base_name: String) -> String:
	var ext := base_name.get_extension()
	var stem := base_name.get_basename()
	var candidate := base_name
	var i := 1
	while FileAccess.file_exists(LIBRARY_DIR.path_join(candidate)):
		candidate = "%s_%d.%s" % [stem, i, ext]
		i += 1
	return candidate
