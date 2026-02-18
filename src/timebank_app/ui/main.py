from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import flet as ft
from flet_color_pickers import MaterialPicker

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

HALF_PULSE = 0.5
PANEL_WIDTH = 860
ADMIN_PASSWORD = "password"


def create_controller(data_dir: Path) -> GameController:
    sounds_dir = data_dir / "sounds"
    sounds_dir.mkdir(parents=True, exist_ok=True)
    return GameController(
        decider=Decider(ADMIN_PASSWORD),
        log_writer=LogWriter(data_dir / "logs" / "events.log"),
        effects=EffectSink(),
        sound_repo=SoundRepo(sounds_dir),
    )


def _format_seconds(value: float) -> str:
    sign = "-" if value < 0 else ""
    total_seconds = int(abs(value))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{sign}{minutes:02d}:{seconds:02d}"


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
        content.append(ft.Text(title, size=36, text_align=ft.TextAlign.CENTER))
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
    page.title = "Turnboard Timebank"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 24

    data_dir = Path("./appdata")
    data_dir.mkdir(exist_ok=True)

    store = ConfigStore(data_dir / "config.ini")
    controller = create_controller(data_dir)

    feedback = ft.Text(color=ft.Colors.RED_300)
    timer_text = ft.Text(size=64, weight=ft.FontWeight.BOLD)
    player_text = ft.Text(size=40, weight=ft.FontWeight.BOLD)
    phase_text = ft.Text(size=20)
    exhausted_text = ft.Text("", color=ft.Colors.RED_300)
    admin_password = ft.TextField(
        label="Пароль администратора", password=True, can_reveal_password=True
    )

    sounds_repo = controller.sound_repo
    game_visible = False

    saved = store.load_game_config()
    if saved:
        setup_players, setup_order, setup_rules, setup_direction = saved
    else:
        setup_players = [
            PlayerConfig(name="Игрок 1", color="#ff9800"),
            PlayerConfig(name="Игрок 2", color="#2196f3"),
        ]
        setup_order = [player.name for player in setup_players]
        setup_rules = Rules(bank_initial=600, cooldown=5, warn_every=60)
        setup_direction = OrderDir.CLOCKWISE

    rules_bank = ft.TextField(
        label="Начальный банк (сек)", value=str(int(setup_rules.bank_initial)), width=200
    )
    rules_cooldown = ft.TextField(
        label="Cooldown (сек)", value=str(int(setup_rules.cooldown)), width=200
    )
    rules_warn = ft.TextField(
        label="warn_every (сек)", value=str(setup_rules.warn_every), width=200
    )
    direction = ft.Dropdown(
        label="Направление",
        options=[
            ft.dropdown.Option(OrderDir.CLOCKWISE.value, "По часовой"),
            ft.dropdown.Option(OrderDir.COUNTERCLOCKWISE.value, "Против часовой"),
        ],
        value=setup_direction.value,
        width=220,
    )

    def persist_current_config() -> None:
        if not controller.state.players:
            return
        store.save_game_config(
            players=controller.state.players,
            order=controller.state.order,
            rules=controller.state.rules,
            order_dir=controller.state.order_dir,
        )

    def persist_setup_config(players: list[PlayerConfig]) -> None:
        try:
            rules = Rules(
                bank_initial=float(rules_bank.value),
                cooldown=float(rules_cooldown.value),
                warn_every=int(rules_warn.value),
            )
        except ValueError:
            return
        store.save_game_config(
            players=players,
            order=[p.name for p in players],
            rules=rules,
            order_dir=OrderDir(direction.value),
        )

    def refresh_tick() -> None:
        if not game_visible:
            return
        if controller.state.mode != Mode.RUNNING:
            return
        controller.dispatch(CmdTick(now_mono=time.monotonic()))
        redraw_game()

    def redraw_game() -> None:
        current = controller.state.current_player
        if not current:
            return
        bank = controller.state.bank.get(current, 0.0)
        timer_text.value = _format_seconds(bank)
        player_text.value = current
        phase_text.value = f"Фаза: {controller.state.turn.phase.value}"
        exhausted_text.value = "ВРЕМЯ ИСЧЕРПАНО" if bank <= 0 else ""

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

    def setup_players_table(players: list[PlayerConfig]) -> ft.DataTable:
        def open_color_picker(player_name: str) -> None:
            target = next((p for p in players if p.name == player_name), None)
            if target is None:
                return

            def on_color_change(event: ft.ControlEvent) -> None:
                target.color = str(event.data)
                show_setup()

            picker = MaterialPicker(color=target.color, on_color_change=on_color_change)
            page.dialog = ft.AlertDialog(title=ft.Text(f"Цвет: {player_name}"), content=picker)
            page.dialog.open = True
            page.update()

        sounds = sounds_repo.list_files()
        rows: list[ft.DataRow] = []
        for idx, player in enumerate(players):
            name_field = ft.TextField(value=player.name, width=180)

            def on_name_change(
                _: ft.ControlEvent, row_idx: int = idx, field: ft.TextField = name_field
            ) -> None:
                players[row_idx].name = field.value.strip() or players[row_idx].name
                persist_setup_config(players)

            name_field.on_blur = on_name_change
            sound_dropdown = ft.Dropdown(
                width=170,
                value=player.sound_tap if player.sound_tap in sounds else None,
                options=[ft.dropdown.Option("", "—")]
                + [ft.dropdown.Option(sound_name) for sound_name in sounds],
            )

            def on_sound_change(
                _: ft.ControlEvent, row_idx: int = idx, dd: ft.Dropdown = sound_dropdown
            ) -> None:
                players[row_idx].sound_tap = dd.value or ""
                persist_setup_config(players)

            sound_dropdown.on_change = on_sound_change
            bank_field = ft.TextField(
                value=str(int(setup_rules.bank_initial)), width=120, disabled=True
            )
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(name_field),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.Container(
                                        width=26, height=26, bgcolor=player.color, border_radius=6
                                    ),
                                    _button(
                                        "Выбрать",
                                        lambda _, name=player.name: open_color_picker(name),
                                    ),
                                ],
                                spacing=10,
                            )
                        ),
                        ft.DataCell(sound_dropdown),
                        ft.DataCell(
                            ft.Column(
                                [bank_field, ft.Text(_format_seconds(setup_rules.bank_initial))]
                            )
                        ),
                    ]
                )
            )
        return ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Имя")),
                ft.DataColumn(ft.Text("Цвет")),
                ft.DataColumn(ft.Text("Звук")),
                ft.DataColumn(ft.Text("Банк_времени")),
            ],
            rows=rows,
            column_spacing=22,
        )

    def pause_players_table() -> ft.DataTable:
        rows: list[ft.DataRow] = []

        def apply_bank(player_name: str, value: str) -> None:
            try:
                seconds = float(value)
            except ValueError:
                feedback.value = "Банк должен быть числом"
                page.update()
                return
            controller.dispatch(
                CmdAdminEdit(
                    now_mono=time.monotonic(),
                    edit_type="set_bank",
                    payload={"player": player_name, "value": seconds},
                )
            )
            persist_current_config()

        for player_name in controller.state.order:
            player_cfg = next((p for p in controller.state.players if p.name == player_name), None)
            color = player_cfg.color if player_cfg else "#FFFFFF"
            sound_tap = player_cfg.sound_tap if player_cfg else ""
            bank_seconds = controller.state.bank.get(player_name, 0.0)
            editable = controller.state.admin_mode

            if editable:
                bank_input = ft.TextField(value=str(int(bank_seconds)), width=120)
                bank_input.on_blur = lambda _, name=player_name, field=bank_input: apply_bank(
                    name, field.value
                )
                bank_control: ft.Control = ft.Column(
                    [bank_input, ft.Text(_format_seconds(bank_seconds))]
                )
            else:
                bank_control = ft.Text(_format_seconds(bank_seconds))

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(player_name)),
                        ft.DataCell(
                            ft.Container(width=26, height=26, bgcolor=color, border_radius=6)
                        ),
                        ft.DataCell(ft.Text(sound_tap or "—")),
                        ft.DataCell(bank_control),
                    ]
                )
            )

        return ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Имя")),
                ft.DataColumn(ft.Text("Цвет")),
                ft.DataColumn(ft.Text("Звук")),
                ft.DataColumn(ft.Text("Банк_времени")),
            ],
            rows=rows,
            column_spacing=22,
        )

    def show_setup() -> None:
        nonlocal game_visible, setup_players, setup_order
        game_visible = False
        page.bgcolor = None
        page.clean()
        feedback.value = ""

        players = [replace(player) for player in setup_players]

        def add_player(_: ft.ControlEvent) -> None:
            next_idx = len(players) + 1
            players.append(PlayerConfig(name=f"Игрок {next_idx}", color="#9e9e9e"))
            persist_setup_config(players)
            show_setup()

        def on_start(_: ft.ControlEvent) -> None:
            nonlocal setup_players, setup_order
            try:
                cleaned_players = []
                for index, player in enumerate(players):
                    name = player.name.strip() or f"Игрок {index + 1}"
                    cleaned_players.append(
                        PlayerConfig(
                            name=name,
                            color=player.color,
                            sound_tap=player.sound_tap,
                        )
                    )
                names = [player.name for player in cleaned_players]
                if len(set(names)) != len(names):
                    feedback.value = "Имена игроков должны быть уникальными"
                    page.update()
                    return

                rules = Rules(
                    bank_initial=float(rules_bank.value),
                    cooldown=float(rules_cooldown.value),
                    warn_every=int(rules_warn.value),
                )
                setup_players = cleaned_players
                setup_order = names
                store.save_game_config(
                    players=setup_players,
                    order=setup_order,
                    rules=rules,
                    order_dir=OrderDir(direction.value),
                )
                controller.dispatch(
                    CmdStartGame(
                        now_mono=time.monotonic(),
                        game_id=str(int(time.time())),
                        players=setup_players,
                        order=setup_order,
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
                setup_players_table(players),
                _button("Добавить игрока", add_player),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(rules_bank, col={"sm": 12, "md": 3}),
                        ft.Container(rules_cooldown, col={"sm": 12, "md": 3}),
                        ft.Container(rules_warn, col={"sm": 12, "md": 3}),
                        ft.Container(direction, col={"sm": 12, "md": 3}),
                    ]
                ),
                _button("Начать игру", on_start),
                feedback,
                title="Настройки игры",
            )
        )

    def show_pause() -> None:
        nonlocal game_visible
        game_visible = False
        page.bgcolor = None
        page.clean()
        feedback.value = ""

        def do_continue(_: ft.ControlEvent) -> None:
            controller.dispatch(CmdPauseOff(now_mono=time.monotonic()))
            show_game()

        def do_admin_auth(_: ft.ControlEvent) -> None:
            controller.dispatch(
                CmdAdminAuth(now_mono=time.monotonic(), password=admin_password.value)
            )
            feedback.value = (
                "Режим администратора включен"
                if controller.state.admin_mode
                else "Неверный пароль администратора"
            )
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
            controller.dispatch(
                CmdAdminEdit(
                    now_mono=time.monotonic(),
                    edit_type="new_game",
                    payload={"game_id": str(int(time.time()))},
                )
            )
            persist_current_config()
            show_game()

        page.add(
            _panel(
                pause_players_table(),
                ft.Divider(),
                ft.Text(f"Текущий игрок: {controller.state.current_player}"),
                ft.Text(f"Фаза: {controller.state.turn.phase.value}"),
                ft.Text(f"Направление: {controller.state.order_dir.value}"),
                _button("Продолжить", do_continue),
                admin_password,
                _button("Войти в режим администратора", do_admin_auth),
                _button("Сменить направление", do_reverse),
                _button("Новая игра", do_new_game),
                feedback,
                title="Техпауза / Настройки",
            )
        )

    def show_game() -> None:
        nonlocal game_visible
        game_visible = True
        page.clean()
        feedback.value = ""

        def do_tap(_: ft.ControlEvent) -> None:
            try:
                controller.dispatch(CmdTap(now_mono=time.monotonic()))
                persist_current_config()
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
            refresh_tick()
            await asyncio.sleep(0.25)

    show_setup()


if __name__ == "__main__":
    run_flet_app()
