extends Node
class_name SoundService

@onready var player: AudioStreamPlayer = AudioStreamPlayer.new()

func _ready() -> void:
	add_child(player)

func play_stream(stream: AudioStream) -> void:
	if stream == null:
		return
	player.stop()
	player.stream = stream
	player.play()

func load_audio_from_path(path_or_uri: String) -> AudioStream:
	var lower: String = path_or_uri.to_lower()
	if lower.ends_with(".mp3"):
		var s: AudioStreamMP3 = AudioStreamMP3.new()
		var err: int = s.load_from_file(path_or_uri)
		if err == OK:
			return s
		return null
	if lower.ends_with(".ogg"):
		var s2: AudioStreamOggVorbis = AudioStreamOggVorbis.new()
		var err2: int = s2.load_from_file(path_or_uri)
		if err2 == OK:
			return s2
		return null
	if lower.ends_with(".wav"):
		var s3: AudioStreamWAV = AudioStreamWAV.new()
		var err3: int = s3.load_from_file(path_or_uri)
		if err3 == OK:
			return s3
		return null
	return null
