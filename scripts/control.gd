extends Control

@onready var button: Button = $CenterContainer/Button
@onready var sfx: AudioStreamPlayer = $AudioStreamPlayer

func _ready() -> void:
	button.pressed.connect(_on_button_pressed)

func _on_button_pressed() -> void:
	# звук
	sfx.play()

	# вибрация (только на мобильных)
	if OS.get_name() == "Android" or OS.get_name() == "iOS":
		# duration_ms, amplitude (0..1) или -1 для дефолтной силы
		Input.vibrate_handheld(60, 0.7)
