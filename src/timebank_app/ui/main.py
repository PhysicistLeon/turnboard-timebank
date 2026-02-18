from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import flet as ft

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
PANEL_WIDTH = 640


def create_controller(data_dir: Path) -> GameController:
    config = ConfigStore(data_dir / "config.ini")
    password = config.get_password() or ""
    return GameController(
        decider=Decider(password),
        log_writer=LogWriter(data_dir / "logs" / "events.log"),
        effects=EffectSink(),
        sound_repo=SoundRepo(data_dir / "sounds"),
    )


def _format_seconds(value: float) -> str:
    return str(int(value))


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

    password_field = ft.TextField(label="Password", password=True, can_reveal_password=True)
    password_confirm = ft.TextField(
        label="Confirm password", password=True, can_reveal_password=True
    )

    players_name = ft.TextField(label="Players comma-separated", value="Alice,Bob,Carol")
    rules_bank = ft.TextField(label="bank_initial sec", value="600")
    rules_cooldown = ft.TextField(label="cooldown sec", value="5")
    rules_warn = ft.TextField(label="warn_every sec", value="60")
    direction = ft.Dropdown(
        label="Direction",
        options=[
            ft.dropdown.Option(OrderDir.CLOCKWISE.value),
            ft.dropdown.Option(OrderDir.COUNTERCLOCKWISE.value),
        ],
        value=OrderDir.CLOCKWISE.value,
    )

    timer_text = ft.Text(size=64, weight=ft.FontWeight.BOLD)
    player_text = ft.Text(size=40, weight=ft.FontWeight.BOLD)
    phase_text = ft.Text(size=20)
    exhausted_text = ft.Text("", color=ft.Colors.RED_300)

    admin_password = ft.TextField(label="Admin password", password=True, can_reveal_password=True)
    game_visible = False

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
        phase_text.value = f"Phase: {controller.state.turn.phase.value}"
        exhausted_text.value = "BANK EXHAUSTED" if bank <= 0 else ""

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

    def show_setup() -> None:
        nonlocal game_visible
        game_visible = False
        page.clean()
        feedback.value = ""

        def on_start(_: ft.ControlEvent) -> None:
            try:
                names = [part.strip() for part in players_name.value.split(",") if part.strip()]
                if len(set(names)) != len(names):
                    feedback.value = "Names must be unique"
                    page.update()
                    return
                players = [
                    PlayerConfig(name=name, color=f"#{(index + 1) * 2:06x}")
                    for index, name in enumerate(names)
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
                        order=[p.name for p in players],
                        order_dir=OrderDir(direction.value),
                        rules=rules,
                    )
                )
                show_game()
            except (ValueError, CommandError) as exc:
                feedback.value = str(exc)
                page.update()

        page.add(
            _panel(
                players_name,
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(rules_bank, col={"sm": 12, "md": 4}),
                        ft.Container(rules_cooldown, col={"sm": 12, "md": 4}),
                        ft.Container(rules_warn, col={"sm": 12, "md": 4}),
                    ]
                ),
                direction,
                _button("Start Game", on_start),
                feedback,
                title="Setup",
            )
        )

    def show_pause() -> None:
        nonlocal game_visible
        game_visible = False
        page.clean()
        feedback.value = ""
        rows: list[ft.Control] = []
        for name in controller.state.order:
            rows.append(
                ft.Row(
                    [
                        ft.Text(name, width=220),
                        ft.Text(_format_seconds(controller.state.bank.get(name, 0.0))),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    width=340,
                )
            )

        def do_continue(_: ft.ControlEvent) -> None:
            controller.dispatch(CmdPauseOff(now_mono=time.monotonic()))
            show_game()

        def do_admin_auth(_: ft.ControlEvent) -> None:
            controller.dispatch(
                CmdAdminAuth(now_mono=time.monotonic(), password=admin_password.value)
            )
            feedback.value = (
                "Admin mode enabled" if controller.state.admin_mode else "Admin password invalid"
            )
            page.update()

        def do_reverse(_: ft.ControlEvent) -> None:
            try:
                controller.dispatch(
                    CmdAdminEdit(
                        now_mono=time.monotonic(),
                        edit_type="reverse",
                        payload={"old": controller.state.order_dir.value},
                    )
                )
                page.update()
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
            show_game()

        page.add(
            _panel(
                ft.Text("Players bank", size=20),
                ft.Column(rows, spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(),
                ft.Text(f"Current: {controller.state.current_player}"),
                ft.Text(f"Phase: {controller.state.turn.phase.value}"),
                ft.Text(f"Direction: {controller.state.order_dir.value}"),
                _button("Continue", do_continue),
                admin_password,
                _button("Enter admin mode", do_admin_auth),
                _button("Reverse direction", do_reverse),
                _button("New Game", do_new_game),
                feedback,
                title="Tech Pause",
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
                [_button("Pause", do_pause), feedback],
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

    if not store.get_password():
        page.clean()

        def save_password(_: ft.ControlEvent) -> None:
            if password_field.value != password_confirm.value:
                feedback.value = "Password mismatch"
                page.update()
                return
            if not password_field.value:
                feedback.value = "Password required"
                page.update()
                return
            store.save_password(password_field.value)
            show_setup()

        page.add(
            _panel(
                password_field,
                password_confirm,
                _button("Continue", save_password),
                feedback,
                title="Create password",
            )
        )
    else:
        show_setup()


if __name__ == "__main__":
    run_flet_app()
