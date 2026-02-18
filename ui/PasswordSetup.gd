extends Control

@onready var pass1 := $VBox/Pass
@onready var pass2 := $VBox/Pass2
@onready var err := $VBox/Error

func _ready() -> void:
	pass1.secret = true
	pass2.secret = true
	$VBox/SaveBtn.pressed.connect(_save)

func _save() -> void:
	var a: String = pass1.text
	var b: String = pass2.text
	if a.length() < 3:
		err.text = "Пароль слишком короткий"
		return
	if a != b:
		err.text = "Пароли не совпадают"
		return
	GameController.storage.set_password(a)
	GameController.storage.save_cfg()
	err.text = ""
	GameController.route_changed.emit("setup")
