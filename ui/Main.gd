extends Control

@onready var root := $ScreenRoot

var _current: Node = null

var scenes := {
	"password": preload("res://ui/PasswordSetup.tscn"),
	"setup": preload("res://ui/Setup.tscn"),
	"game": preload("res://ui/Game.tscn"),
	"pause": preload("res://ui/Pause.tscn"),
}

func _ready() -> void:
	GameController.route_changed.connect(_on_route)
	var initial_route: String = GameController.get_current_route()
	if initial_route == "":
		initial_route = "password"
	_on_route(initial_route)

func _on_route(route: String) -> void:
	if not scenes.has(route):
		return
	if _current != null:
		_current.queue_free()
	_current = scenes[route].instantiate()
	root.add_child(_current)
