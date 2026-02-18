extends Control

@onready var root: Control = $ScreenRoot

var _current: Node = null

var scenes: Dictionary = {
	"password": preload("res://ui/PasswordSetup.tscn"),
	"setup": preload("res://ui/Setup.tscn"),
	"game": preload("res://ui/Game.tscn"),
	"pause": preload("res://ui/Pause.tscn"),
}

func _ready() -> void:
	GameController.route_changed.connect(_on_route)
	_on_route("password")

func _on_route(route: String) -> void:
	if not scenes.has(route):
		return
	if _current != null:
		_current.queue_free()
	var next_scene: PackedScene = scenes[route]
	_current = next_scene.instantiate()
	root.add_child(_current)
