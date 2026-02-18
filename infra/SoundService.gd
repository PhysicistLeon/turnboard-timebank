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
		var s: AudioStreamMP3 = AudioStreamMP3.load_from_file(path_or_uri)
		return s
	if lower.ends_with(".ogg"):
		var s2: AudioStreamOggVorbis = AudioStreamOggVorbis.load_from_file(path_or_uri)
		return s2
	if lower.ends_with(".wav"):
		var s3: AudioStreamWAV = AudioStreamWAV.load_from_file(path_or_uri)
		return s3
	return null
