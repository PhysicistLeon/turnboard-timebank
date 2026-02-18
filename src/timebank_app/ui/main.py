from __future__ import annotations

import time
from pathlib import Path

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
)
from timebank_app.domain.engine import CommandError, Decider
from timebank_app.domain.models import OrderDir, PlayerConfig, Rules
from timebank_app.infra.effects import EffectSink, SoundRepo
from timebank_app.infra.logging import LogWriter
from timebank_app.infra.storage import ConfigStore


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


def app_main(page: ft.Page) -> None:
    page.title = "Turnboard Timebank"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK

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
        page.bgcolor = color if pulse > 0.5 else "#000000"
        page.update()

    def show_setup() -> None:
        page.clean()

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
            ft.Text("Setup", size=40),
            players_name,
            ft.Row([rules_bank, rules_cooldown, rules_warn]),
            direction,
            ft.ElevatedButton("Start Game", on_click=on_start),
            feedback,
        )

    def show_pause() -> None:
        page.clean()
        rows: list[ft.Control] = [ft.Text("Tech Pause", size=36)]
        for name in controller.state.order:
            rows.append(ft.Text(f"{name}: {_format_seconds(controller.state.bank.get(name, 0.0))}"))

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

        rows.extend(
            [
                ft.Text(f"Current: {controller.state.current_player}"),
                ft.Text(f"Phase: {controller.state.turn.phase.value}"),
                ft.Text(f"Direction: {controller.state.order_dir.value}"),
                ft.ElevatedButton("Continue", on_click=do_continue),
                admin_password,
                ft.ElevatedButton("Enter admin mode", on_click=do_admin_auth),
                ft.ElevatedButton("Reverse direction", on_click=do_reverse),
                ft.ElevatedButton("New Game", on_click=do_new_game),
                feedback,
            ]
        )
        page.add(*rows)

    def show_game() -> None:
        page.clean()

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

        page.on_app_lifecycle_state_change = (
            lambda event: controller.dispatch(CmdBackground(now_mono=time.monotonic()))
            if event.data == ft.AppLifecycleState.PAUSED
            else None
        )

        big_button = ft.Container(
            width=page.width or 420,
            height=(page.height or 800) * 0.7,
            border_radius=24,
            bgcolor=ft.Colors.BLACK,
            content=ft.Column(
                [player_text, timer_text, phase_text, exhausted_text],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=do_tap,
            ink=True,
        )
        page.add(big_button, ft.Row([ft.ElevatedButton("Pause", on_click=do_pause), feedback]))
        redraw_game()

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
            ft.Text("Create password", size=36),
            password_field,
            password_confirm,
            ft.ElevatedButton("Continue", on_click=save_password),
            feedback,
        )
    else:
        show_setup()


if __name__ == "__main__":
    ft.app(target=app_main)
