from __future__ import annotations

import asyncio
import importlib
import importlib.util
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import flet as ft
import flet_audio as fta

from timebank_app.app.controller import GameController
from timebank_app.domain.commands import (
    CmdAdminAuth,
    CmdAdminEdit,
    CmdBackground,
    CmdPauseOff,
    CmdPauseOn,
    CmdStartGame,
    CmdTap,
    CmdTick,
)
from timebank_app.domain.engine import CommandError, Decider
from timebank_app.domain.models import Mode, OrderDir, PlayerConfig, Rules
from timebank_app.infra.effects import EffectSink, SoundRepo
from timebank_app.infra.logging import LogWriter
from timebank_app.infra.storage import ConfigStore
from timebank_app.ui.formatting import format_mm_ss

HALF_PULSE = 0.5
PANEL_WIDTH = 960
ADMIN_PASSWORD = "password"


def create_controller(data_dir: Path) -> GameController:
    return GameController(
        decider=Decider(ADMIN_PASSWORD),
        log_writer=LogWriter(data_dir / "logs" / "events.log"),
        effects=EffectSink(),
        sound_repo=SoundRepo(data_dir / "sounds"),
    )


def _button(label: str, on_click) -> ft.Control:  # type: ignore[no-untyped-def]
    button_cls = getattr(ft, "Button", None)
    if button_cls is not None:
        for builder in (
            lambda: button_cls(text=label, on_click=on_click),
            lambda: button_cls(label, on_click=on_click),
        ):
            try:
                return builder()
            except TypeError:
                continue

    elevated_cls = getattr(ft, "ElevatedButton", None)
    if elevated_cls is None:
        raise RuntimeError("No compatible button control found in flet module")
    try:
        return elevated_cls(text=label, on_click=on_click)
    except TypeError:
        return elevated_cls(label, on_click=on_click)


def _is_background_lifecycle_state(event_data: Any) -> bool:
    text = str(event_data).lower()
    return any(keyword in text for keyword in ("pause", "inactive", "hide", "background"))


def _center_alignment() -> Any:
    alignment_module = getattr(ft, "alignment", None)
    if alignment_module is not None and hasattr(alignment_module, "center"):
        return alignment_module.center
    return ft.Alignment(0, 0)


def _panel(*controls: ft.Control, title: str | None = None) -> ft.Control:
    content: list[ft.Control] = []
    if title:
        content.append(ft.Text(title, size=40, text_align=ft.TextAlign.CENTER))
    content.extend(controls)

    return ft.Container(
        width=PANEL_WIDTH,
        padding=20,
        border_radius=20,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
        content=ft.Column(
            controls=content,
            spacing=16,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )


def _load_color_picker_parts() -> tuple[Any | None, Any | None, Any | None] | None:
    if importlib.util.find_spec("flet_color_pickers") is None:
        return None
    module = importlib.import_module("flet_color_pickers")
    return (
        getattr(module, "ColorPicker", None),
        getattr(module, "PaletteType", None),
        getattr(module, "ColorLabelType", None),
    )


def _dropdown(
    *,
    options: list[Any],
    value: str | None = None,
    width: int | None = None,
    label: str | None = None,
    on_change=None,
) -> ft.Dropdown:  # type: ignore[no-untyped-def]
    control = ft.Dropdown(options=options, value=value, width=width, label=label)
    if on_change is not None:
        control.on_change = on_change
    return control


def run_flet_app() -> None:
    run_fn = getattr(ft, "run", None)
    if callable(run_fn):
        run_fn(app_main)
        return

    app_fn = getattr(ft, "app", None)
    if callable(app_fn):
        app_fn(target=app_main)
        return

    raise RuntimeError("Flet module has no run() or app() entrypoint")


def app_main(page: ft.Page) -> None:
    page.title = "Таймбанк ходов"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 24

    data_dir = Path("./appdata")
    data_dir.mkdir(exist_ok=True)
    (data_dir / "sounds").mkdir(exist_ok=True)

    store = ConfigStore(data_dir / "config.ini")
    controller = create_controller(data_dir)
    feedback = ft.Text(color=ft.Colors.RED_300)
    color_picker_parts = _load_color_picker_parts()

    rules_bank = ft.TextField(label="Базовый банк (сек)", value="600", width=220)
    rules_cooldown = ft.TextField(label="Cooldown (сек)", value="5", width=220)
    rules_warn = ft.TextField(label="warn_every (сек)", value="60", width=220)
    direction = ft.Dropdown(
        label="Направление",
        options=[
            ft.dropdown.Option(OrderDir.CLOCKWISE.value, "По часовой"),
            ft.dropdown.Option(OrderDir.COUNTERCLOCKWISE.value, "Против часовой"),
        ],
        value=OrderDir.CLOCKWISE.value,
        width=220,
    )
    new_player_name = ft.TextField(label="Имя нового игрока", width=240)

    timer_text = ft.Text(size=64, weight=ft.FontWeight.BOLD)
    player_text = ft.Text(size=40, weight=ft.FontWeight.BOLD)
    phase_text = ft.Text(size=20)
    exhausted_text = ft.Text("", color=ft.Colors.RED_300)
    admin_password = ft.TextField(
        label="Пароль администратора",
        password=True,
        can_reveal_password=True,
    )

    game_visible = False
    setup_players = [
        PlayerConfig(name="Alice", color="#FFC107"),
        PlayerConfig(name="Bob", color="#03A9F4"),
        PlayerConfig(name="Carol", color="#8BC34A"),
    ]

    saved = store.load_game_config()
    if saved:
        setup_players = saved["players"]
        direction.value = saved["order_dir"].value
        rules = saved["rules"]
        rules_bank.value = str(int(rules.bank_initial))
        rules_cooldown.value = str(int(rules.cooldown))
        rules_warn.value = str(rules.warn_every)

    def persist_current_config() -> None:
        if controller.state.players:
            players = controller.state.players
            order = controller.state.order
            order_dir_value = controller.state.order_dir
            rules_value = controller.state.rules
        else:
            players = setup_players
            order = [player.name for player in setup_players]
            order_dir_value = OrderDir(direction.value)
            rules_value = Rules(
                bank_initial=float(rules_bank.value or 0),
                cooldown=float(rules_cooldown.value or 0),
                warn_every=int(rules_warn.value or 1),
            )

        store.save_game_config(
            players=players,
            order=order,
            order_dir=order_dir_value,
            rules=rules_value,
        )

    audio_player = fta.Audio(
        autoplay=False,
        release_mode=fta.ReleaseMode.STOP,
    )
    page.services.append(audio_player)

    async def play_sound_by_name(sound_name: str) -> None:
        if not sound_name:
            return
        source = controller.sound_repo.resolve(sound_name)
        if source is None:
            feedback.value = f"Звук не найден: {sound_name}"
            page.update()
            return
        audio_player.src = str(source.resolve())
        await audio_player.play(0)

    async def play_sounds_for_events(events: list[Any]) -> None:
        queued: list[str] = []
        for event in events:
            if event.event_type == "TURN_END":
                player = event.data.get("player", "")
                for cfg in controller.state.players:
                    if cfg.name == player and cfg.sound_tap:
                        queued.append(cfg.sound_tap)
                        break
            if event.event_type == "WARN_LONG_TURN" and controller.state.rules.warn_sound:
                queued.append(controller.state.rules.warn_sound)

        for sound_name in queued:
            await play_sound_by_name(sound_name)

    def sound_options() -> list[ft.dropdown.Option]:
        files = controller.sound_repo.list_files()
        options = [ft.dropdown.Option("", "—")]
        if files:
            options.append(ft.dropdown.Option("__random__", "Случайный звук"))
        options.extend(ft.dropdown.Option(name) for name in files)
        return options

    def open_color_picker(
        player_name: str,
        initial_color: str,
        on_selected: Callable[[str], None],
    ) -> None:
        if color_picker_parts is None:
            feedback.value = "Color picker недоступен: установите flet-color-pickers"
            page.update()
            return

        color_picker_cls, palette_type_cls, color_label_type_cls = color_picker_parts
        if color_picker_cls is None:
            feedback.value = "ColorPicker недоступен в flet-color-pickers"
            page.update()
            return

        picker_kwargs = {
            "color": initial_color,
            "on_color_change": lambda event: on_selected(event.data),
        }
        if palette_type_cls is not None and hasattr(palette_type_cls, "RGB_WITH_GREEN"):
            picker_kwargs["palette_type"] = palette_type_cls.RGB_WITH_GREEN
        if color_label_type_cls is not None and all(
            hasattr(color_label_type_cls, attr) for attr in ("HEX", "RGB")
        ):
            picker_kwargs["label_types"] = [
                color_label_type_cls.HEX,
                color_label_type_cls.RGB,
            ]

        picker = color_picker_cls(**picker_kwargs)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Выбор цвета: {player_name}"),
            content=ft.Container(picker, width=420, height=420),
            actions=[_button("Закрыть", lambda _: close_dialog())],
        )

        def close_dialog() -> None:
            dialog.open = False
            page.update()

        page.dialog = dialog
        dialog.open = True
        page.update()

    async def refresh_tick() -> None:
        if not game_visible:
            return
        if controller.state.mode != Mode.RUNNING:
            return
        result = controller.dispatch(CmdTick(now_mono=time.monotonic()))
        await play_sounds_for_events(result.events)
        redraw_game()

    def redraw_game() -> None:
        current = controller.state.current_player
        if not current:
            return

        bank = controller.state.bank.get(current, 0.0)
        timer_text.value = format_mm_ss(bank)
        player_text.value = current
        phase_text.value = f"Фаза: {controller.state.turn.phase.value}"
        exhausted_text.value = "БАНК ИСЧЕРПАН" if bank <= 0 else ""

        color = "#000000"
        for cfg in controller.state.players:
            if cfg.name == current:
                color = cfg.color
                break

        left = max(0.0, bank)
        fraction = (
            0.0
            if controller.state.rules.bank_initial <= 0
            else 1.0 - min(1.0, left / controller.state.rules.bank_initial)
        )
        hz = controller.state.rules.blink_min_hz + fraction * (
            controller.state.rules.blink_max_hz - controller.state.rules.blink_min_hz
        )
        pulse = (time.time() * hz) % 1.0
        page.bgcolor = color if pulse > HALF_PULSE else "#000000"
        page.update()

    def build_setup_table() -> ft.DataTable:
        rows: list[ft.DataRow] = []

        for idx, player in enumerate(setup_players):
            name_field = ft.TextField(value=player.name, width=160)
            sound_field = _dropdown(
                options=sound_options(),
                value=player.sound_tap,
                width=180,
            )

            def on_name_change(event: ft.ControlEvent, index: int = idx) -> None:
                setup_players[index].name = event.control.value.strip()

            def on_sound_change(event: ft.ControlEvent, index: int = idx) -> None:
                setup_players[index].sound_tap = event.control.value or ""

            name_field.on_change = on_name_change
            sound_field.on_change = on_sound_change

            color_preview = ft.Container(width=26, height=26, bgcolor=player.color, border_radius=6)

            def on_color_selected(
                value: str,
                index: int = idx,
                preview: ft.Container = color_preview,
            ) -> None:
                setup_players[index].color = value
                preview.bgcolor = value
                page.update()

            current_name = player.name
            current_color = player.color
            color_button = _button(
                "Цвет",
                lambda _, name=current_name, color=current_color: open_color_picker(
                    name,
                    color,
                    lambda selected, n=name: on_color_selected_by_name(n, selected),
                ),
            )

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(idx + 1))),
                        ft.DataCell(name_field),
                        ft.DataCell(ft.Row([color_preview, color_button])),
                        ft.DataCell(sound_field),
                        ft.DataCell(ft.Text(format_mm_ss(float(rules_bank.value or 0)))),
                        ft.DataCell(
                            _button("Удалить", lambda _, index=idx: remove_setup_player(index))
                        ),
                    ]
                )
            )

        return ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("#")),
                ft.DataColumn(ft.Text("Имя")),
                ft.DataColumn(ft.Text("Цвет")),
                ft.DataColumn(ft.Text("Звук")),
                ft.DataColumn(ft.Text("Банк времени")),
                ft.DataColumn(ft.Text("Действия")),
            ],
            rows=rows,
        )

    def on_color_selected_by_name(player_name: str, selected_color: str) -> None:
        for player in setup_players:
            if player.name == player_name:
                player.color = selected_color
                break
        show_setup()

    def remove_setup_player(index: int) -> None:
        if len(setup_players) <= 1:
            feedback.value = "Нужен хотя бы один игрок"
            page.update()
            return
        setup_players.pop(index)
        show_setup()

    def show_setup() -> None:
        nonlocal game_visible
        game_visible = False
        page.clean()
        feedback.value = ""

        table = build_setup_table()

        def do_add_player(_: ft.ControlEvent) -> None:
            name = new_player_name.value.strip()
            if not name:
                feedback.value = "Введите имя игрока"
                page.update()
                return
            if any(item.name == name for item in setup_players):
                feedback.value = "Имена игроков должны быть уникальны"
                page.update()
                return
            setup_players.append(PlayerConfig(name=name, color="#FFFFFF"))
            new_player_name.value = ""
            persist_current_config()
            show_setup()

        def on_start(_: ft.ControlEvent) -> None:
            try:
                names = [player.name.strip() for player in setup_players if player.name.strip()]
                if len(names) != len(setup_players):
                    feedback.value = "Имя игрока не может быть пустым"
                    page.update()
                    return
                if len(set(names)) != len(names):
                    feedback.value = "Имена игроков должны быть уникальны"
                    page.update()
                    return

                players = [
                    PlayerConfig(
                        name=player.name.strip(),
                        color=player.color,
                        sound_tap=player.sound_tap,
                    )
                    for player in setup_players
                ]
                rules = Rules(
                    bank_initial=float(rules_bank.value),
                    cooldown=float(rules_cooldown.value),
                    warn_every=int(rules_warn.value),
                )
                controller.dispatch(
                    CmdStartGame(
                        now_mono=time.monotonic(),
                        game_id=str(int(time.time())),
                        players=players,
                        order=[player.name for player in players],
                        order_dir=OrderDir(direction.value),
                        rules=rules,
                    )
                )
                persist_current_config()
                show_game()
            except (ValueError, CommandError) as exc:
                feedback.value = str(exc)
                page.update()

        page.add(
            _panel(
                ft.Text("Настройки (до старта)", size=24),
                table,
                ft.Row([new_player_name, _button("Добавить игрока", do_add_player)]),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(rules_bank, col={"sm": 12, "md": 3}),
                        ft.Container(rules_cooldown, col={"sm": 12, "md": 3}),
                        ft.Container(rules_warn, col={"sm": 12, "md": 3}),
                        ft.Container(direction, col={"sm": 12, "md": 3}),
                    ]
                ),
                _button("Старт игры", on_start),
                feedback,
                title="Setup",
            )
        )

    def apply_pause_edit(player_name: str, edit_type: str, payload: dict) -> None:
        try:
            controller.dispatch(
                CmdAdminEdit(
                    now_mono=time.monotonic(),
                    edit_type=edit_type,
                    payload=payload,
                )
            )
            persist_current_config()
            show_pause()
        except (CommandError, ValueError) as exc:
            feedback.value = str(exc)
            page.update()

    def pause_player_row(player_name: str) -> ft.DataRow:
        cfg = next(item for item in controller.state.players if item.name == player_name)
        bank_seconds = controller.state.bank.get(player_name, 0.0)
        editable = controller.state.admin_mode

        if editable:
            name_control: ft.Control = ft.TextField(
                value=cfg.name,
                width=160,
                on_submit=lambda e: apply_pause_edit(
                    player_name,
                    "rename_player",
                    {"old": player_name, "new": e.control.value.strip()},
                ),
            )
            sound_control: ft.Control = _dropdown(
                width=180,
                options=sound_options(),
                value=cfg.sound_tap,
                on_change=lambda e: apply_pause_edit(
                    player_name,
                    "set_sound_tap",
                    {"player": player_name, "value": e.control.value or ""},
                ),
            )
            bank_field = ft.TextField(
                value=str(int(bank_seconds)),
                width=120,
            )

            def apply_bank(_=None) -> None:
                apply_pause_edit(
                    player_name,
                    "set_bank",
                    {"player": player_name, "value": float(bank_field.value)},
                )

            bank_field.on_submit = apply_bank
            bank_field.on_blur = apply_bank
            bank_control: ft.Control = ft.Row([bank_field, _button("OK", apply_bank)])

            color_button = _button(
                "Цвет",
                lambda _, name=player_name, color=cfg.color: open_color_picker(
                    name,
                    color,
                    lambda selected: apply_pause_edit(
                        name,
                        "set_color",
                        {"player": name, "value": selected},
                    ),
                ),
            )
            color_control: ft.Control = ft.Row(
                [
                    ft.Container(
                        width=26,
                        height=26,
                        bgcolor=cfg.color,
                        border_radius=6,
                    ),
                    color_button,
                ]
            )
            action_control: ft.Control = _button(
                "Удалить",
                lambda _: apply_pause_edit(
                    player_name,
                    "remove_player",
                    {"player": player_name},
                ),
            )
        else:
            name_control = ft.Text(cfg.name)
            sound_control = ft.Text(cfg.sound_tap or "—")
            bank_control = ft.Text(f"{format_mm_ss(bank_seconds)} ({int(bank_seconds)}s)")
            color_control = ft.Row(
                [
                    ft.Container(
                        width=26,
                        height=26,
                        bgcolor=cfg.color,
                        border_radius=6,
                    ),
                    ft.Text(cfg.color),
                ]
            )
            action_control = ft.Text("—")

        return ft.DataRow(
            cells=[
                ft.DataCell(name_control),
                ft.DataCell(color_control),
                ft.DataCell(sound_control),
                ft.DataCell(bank_control),
                ft.DataCell(action_control),
            ]
        )

    def show_pause() -> None:
        nonlocal game_visible
        game_visible = False
        page.clean()
        feedback.value = ""

        def do_continue(_: ft.ControlEvent) -> None:
            controller.dispatch(CmdPauseOff(now_mono=time.monotonic()))
            show_game()

        def do_admin_auth(_: ft.ControlEvent) -> None:
            controller.dispatch(
                CmdAdminAuth(
                    now_mono=time.monotonic(),
                    password=admin_password.value,
                )
            )
            feedback.value = (
                "Режим администратора включен"
                if controller.state.admin_mode
                else "Неверный пароль администратора"
            )
            page.update()
            show_pause()

        def do_reverse(_: ft.ControlEvent) -> None:
            try:
                controller.dispatch(
                    CmdAdminEdit(
                        now_mono=time.monotonic(),
                        edit_type="reverse",
                        payload={"old": controller.state.order_dir.value},
                    )
                )
                persist_current_config()
                show_pause()
            except CommandError as exc:
                feedback.value = str(exc)
                page.update()

        def do_new_game(_: ft.ControlEvent) -> None:
            try:
                controller.dispatch(
                    CmdAdminEdit(
                        now_mono=time.monotonic(),
                        edit_type="new_game",
                        payload={"game_id": str(int(time.time()))},
                    )
                )
                persist_current_config()
                show_game()
            except CommandError as exc:
                feedback.value = str(exc)
                page.update()

        rows = [pause_player_row(name) for name in controller.state.order]

        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Имя")),
                ft.DataColumn(ft.Text("Цвет")),
                ft.DataColumn(ft.Text("Звук")),
                ft.DataColumn(ft.Text("Банк времени")),
                ft.DataColumn(ft.Text("Действия")),
            ],
            rows=rows,
        )

        page.add(
            _panel(
                ft.Text("Таблица игроков", size=20),
                table,
                ft.Divider(),
                ft.Text(f"Текущий: {controller.state.current_player}"),
                ft.Text(f"Фаза: {controller.state.turn.phase.value}"),
                ft.Text(f"Направление: {controller.state.order_dir.value}"),
                _button("Продолжить", do_continue),
                admin_password,
                _button("Войти в режим администратора", do_admin_auth),
                _button("Сменить направление", do_reverse),
                _button("Новая игра", do_new_game),
                feedback,
                title="Tech Pause",
            )
        )

    def show_game() -> None:
        nonlocal game_visible
        game_visible = True
        page.clean()
        feedback.value = ""

        async def do_tap(_: ft.ControlEvent) -> None:
            try:
                result = controller.dispatch(CmdTap(now_mono=time.monotonic()))
                await play_sounds_for_events(result.events)
                redraw_game()
            except CommandError as exc:
                feedback.value = str(exc)
                page.update()

        def do_pause(_: ft.ControlEvent) -> None:
            controller.dispatch(CmdPauseOn(now_mono=time.monotonic(), cause="manual"))
            show_pause()

        def on_lifecycle_change(event: ft.ControlEvent) -> None:
            if _is_background_lifecycle_state(event.data):
                controller.dispatch(CmdBackground(now_mono=time.monotonic()))
                show_pause()

        page.on_app_lifecycle_state_change = on_lifecycle_change

        big_button = ft.Container(
            width=min(page.width or 900, 900),
            height=(page.height or 800) * 0.7,
            border_radius=24,
            bgcolor=ft.Colors.BLACK,
            alignment=_center_alignment(),
            padding=24,
            content=ft.Column(
                [player_text, timer_text, phase_text, exhausted_text],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=do_tap,
            ink=True,
        )
        page.add(
            big_button,
            ft.Row(
                [_button("Пауза", do_pause), feedback],
                width=min(page.width or 900, 900),
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )
        page.run_task(_ticker_loop)
        redraw_game()

    async def _ticker_loop() -> None:
        while game_visible:
            await refresh_tick()
            await asyncio.sleep(0.25)

    show_setup()


if __name__ == "__main__":
    run_flet_app()
