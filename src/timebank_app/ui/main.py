from __future__ import annotations

import asyncio
import time
from copy import deepcopy
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

try:
    from flet_color_pickers import MaterialPicker
except ImportError:  # pragma: no cover - fallback for environments without picker package
    MaterialPicker = None

HALF_PULSE = 0.5
PANEL_WIDTH = 900
ADMIN_PASSWORD = "password"
DEFAULT_PLAYERS = ["Алиса", "Боб", "Кэрол"]


def create_controller(data_dir: Path) -> GameController:
    return GameController(
        decider=Decider(ADMIN_PASSWORD),
        log_writer=LogWriter(data_dir / "logs" / "events.log"),
        effects=EffectSink(),
        sound_repo=SoundRepo(data_dir / "sounds"),
    )


def _format_mmss(value: float) -> str:
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
        content.append(ft.Text(title, size=34, text_align=ft.TextAlign.CENTER))
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
    (data_dir / "sounds").mkdir(parents=True, exist_ok=True)

    store = ConfigStore(data_dir / "config.ini")
    controller = create_controller(data_dir)

    loaded = store.load_game_config()
    if loaded:
        setup_players, setup_order, setup_dir, setup_rules = loaded
    else:
        setup_players = [PlayerConfig(name=name) for name in DEFAULT_PLAYERS]
        setup_dir = OrderDir.CLOCKWISE
        setup_rules = Rules(bank_initial=600, cooldown=5, warn_every=60)

    setup_players = deepcopy(setup_players)
    feedback = ft.Text(color=ft.Colors.RED_300)
    info_text = ft.Text(color=ft.Colors.BLUE_200)
    admin_password = ft.TextField(
        label="Пароль администратора",
        password=True,
        can_reveal_password=True,
    )

    rules_bank = ft.TextField(
        label="Банк времени (сек)",
        value=str(int(setup_rules.bank_initial)),
        width=220,
    )
    rules_cooldown = ft.TextField(
        label="Cooldown (сек)",
        value=str(int(setup_rules.cooldown)),
        width=220,
    )
    rules_warn = ft.TextField(
        label="Warn every (сек)",
        value=str(int(setup_rules.warn_every)),
        width=220,
    )
    direction = ft.Dropdown(
        label="Направление",
        options=[
            ft.dropdown.Option(OrderDir.CLOCKWISE.value, "clockwise"),
            ft.dropdown.Option(OrderDir.COUNTERCLOCKWISE.value, "counterclockwise"),
        ],
        value=setup_dir.value,
        width=220,
    )

    timer_text = ft.Text(size=64, weight=ft.FontWeight.BOLD)
    player_text = ft.Text(size=40, weight=ft.FontWeight.BOLD)
    phase_text = ft.Text(size=20)
    exhausted_text = ft.Text("", color=ft.Colors.RED_300)
    game_visible = False

    def sound_options() -> list[ft.dropdown.Option]:
        names = controller.sound_repo.list_files()
        return [ft.dropdown.Option(name) for name in names]

    def player_for_name(name: str) -> PlayerConfig | None:
        for player in setup_players:
            if player.name == name:
                return player
        return None

    def persist_setup_config() -> None:
        try:
            rules = Rules(
                bank_initial=float(rules_bank.value),
                cooldown=float(rules_cooldown.value),
                warn_every=int(rules_warn.value),
            )
            if not setup_players:
                return
            store.save_game_config(
                players=setup_players,
                order=[player.name for player in setup_players],
                order_dir=OrderDir(direction.value),
                rules=rules,
            )
        except (ValueError, TypeError):
            return

    def open_color_dialog(player: PlayerConfig, on_refresh) -> None:  # type: ignore[no-untyped-def]
        feedback.value = ""
        if MaterialPicker is None:
            feedback.value = "Color picker недоступен, используйте HEX в конфиге."
            page.update()
            return

        current_color = player.color

        def on_color_change(event: ft.ControlEvent) -> None:
            nonlocal current_color
            current_color = event.data or current_color

        picker = MaterialPicker(color=player.color, on_color_change=on_color_change)

        def do_apply(_: ft.ControlEvent) -> None:
            player.color = current_color
            on_refresh()
            page.close(color_dialog)

        color_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Выбор цвета: {player.name}"),
            content=ft.Container(width=500, height=420, content=picker),
            actions=[
                _button("Отмена", lambda _: page.close(color_dialog)),
                _button("Применить", do_apply),
            ],
        )
        page.open(color_dialog)

    def make_players_table(
        editable: bool,
        bank_source: dict[str, float],
        on_change,
        allow_bank_edit: bool,
    ) -> ft.DataTable:  # type: ignore[no-untyped-def]
        rows: list[ft.DataRow] = []
        options = sound_options()
        for index, player in enumerate(setup_players):
            bank_value = bank_source.get(player.name, float(rules_bank.value or "0"))
            name_control: ft.Control
            if editable:
                name_field = ft.TextField(value=player.name, dense=True)

                def on_name_change(event: ft.ControlEvent, row_index=index) -> None:
                    new_name = event.control.value.strip()
                    if not new_name:
                        feedback.value = "Имя игрока не может быть пустым."
                        page.update()
                        return
                    if any(
                        idx != row_index and candidate.name == new_name
                        for idx, candidate in enumerate(setup_players)
                    ):
                        feedback.value = "Имена игроков должны быть уникальными."
                        page.update()
                        return
                    old_name = setup_players[row_index].name
                    setup_players[row_index].name = new_name
                    if old_name in bank_source:
                        bank_source[new_name] = bank_source.pop(old_name)
                    on_change()

                name_field.on_submit = on_name_change
                name_field.on_blur = on_name_change
                name_control = name_field
            else:
                name_control = ft.Text(player.name)

            color_cell = ft.Row(
                controls=[
                    ft.Container(width=24, height=24, bgcolor=player.color, border_radius=4),
                    ft.Text(player.color),
                    _button(
                        "Цвет",
                        lambda _, selected=player: open_color_dialog(selected, on_change),
                    )
                    if editable
                    else ft.Container(),
                ],
                spacing=8,
            )

            if editable:
                dropdown = ft.Dropdown(options=options, value=player.sound_tap or None, width=170)

                def on_sound_change(event: ft.ControlEvent, selected=player) -> None:
                    selected.sound_tap = event.data or ""
                    on_change()

                dropdown.on_change = on_sound_change
                sound_control = dropdown
            else:
                sound_control = ft.Text(player.sound_tap or "—")

            bank_control: ft.Control
            if editable and allow_bank_edit:
                bank_field = ft.TextField(value=str(int(bank_value)), dense=True, width=120)

                def on_bank_change(event: ft.ControlEvent, selected=player) -> None:
                    try:
                        bank_source[selected.name] = float(event.control.value)
                        on_change()
                    except ValueError:
                        feedback.value = "Банк времени должен быть числом секунд."
                        page.update()

                bank_field.on_submit = on_bank_change
                bank_field.on_blur = on_bank_change
                bank_control = bank_field
            else:
                bank_control = ft.Text(_format_mmss(bank_value))

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(name_control),
                        ft.DataCell(color_cell),
                        ft.DataCell(sound_control),
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
            heading_row_height=44,
            data_row_min_height=56,
            data_row_max_height=74,
        )

    def add_player() -> None:
        new_name = f"Игрок {len(setup_players) + 1}"
        while player_for_name(new_name):
            new_name += "_"
        setup_players.append(PlayerConfig(name=new_name, color="#FFFFFF"))
        persist_setup_config()

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
        timer_text.value = _format_mmss(bank)
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

    def show_setup() -> None:
        nonlocal game_visible
        game_visible = False
        page.clean()
        feedback.value = ""
        info_text.value = ""

        setup_bank_source = {
            player.name: float(rules_bank.value or "0") for player in setup_players
        }

        def on_table_changed() -> None:
            persist_setup_config()
            show_setup()

        table = make_players_table(
            editable=True,
            bank_source=setup_bank_source,
            on_change=on_table_changed,
            allow_bank_edit=True,
        )

        def on_start(_: ft.ControlEvent) -> None:
            try:
                if len(setup_players) < 2:
                    feedback.value = "Нужно минимум 2 игрока."
                    page.update()
                    return
                names = [player.name for player in setup_players]
                if len(set(names)) != len(names):
                    feedback.value = "Имена игроков должны быть уникальными."
                    page.update()
                    return
                rules = Rules(
                    bank_initial=float(rules_bank.value),
                    cooldown=float(rules_cooldown.value),
                    warn_every=int(rules_warn.value),
                )
                persist_setup_config()
                controller.dispatch(
                    CmdStartGame(
                        now_mono=time.monotonic(),
                        game_id=str(int(time.time())),
                        players=deepcopy(setup_players),
                        order=[player.name for player in setup_players],
                        order_dir=OrderDir(direction.value),
                        rules=rules,
                    )
                )
                for player in setup_players:
                    controller.dispatch(
                        CmdAdminEdit(
                            now_mono=time.monotonic(),
                            edit_type="set_bank",
                            payload={
                                "player": player.name,
                                "value": setup_bank_source[player.name],
                            },
                        )
                    )
                show_game()
            except (ValueError, CommandError) as exc:
                feedback.value = str(exc)
                page.update()

        page.add(
            _panel(
                ft.Text("Настройки партии", size=24),
                table,
                ft.Row(
                    [
                        _button("Добавить игрока", lambda _: (add_player(), show_setup())),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
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
                info_text,
                title="Setup",
            )
        )

    def show_pause() -> None:
        nonlocal game_visible
        game_visible = False
        page.clean()
        feedback.value = ""
        info_text.value = ""

        bank_snapshot = dict(controller.state.bank)
        editable = controller.state.admin_mode

        def on_table_changed() -> None:
            nonlocal bank_snapshot
            bank_snapshot = dict(bank_snapshot)
            show_pause()

        table = make_players_table(
            editable=editable,
            bank_source=bank_snapshot,
            on_change=on_table_changed,
            allow_bank_edit=editable,
        )

        def apply_admin_changes() -> None:
            if not controller.state.admin_mode:
                return
            state_players = {player.name: player for player in controller.state.players}
            for player in setup_players:
                original = state_players.get(player.name)
                if original is None:
                    continue
                if original.color != player.color:
                    controller.dispatch(
                        CmdAdminEdit(
                            now_mono=time.monotonic(),
                            edit_type="set_color",
                            payload={"player": player.name, "value": player.color},
                        )
                    )
                if original.sound_tap != player.sound_tap:
                    controller.dispatch(
                        CmdAdminEdit(
                            now_mono=time.monotonic(),
                            edit_type="set_sound_tap",
                            payload={"player": player.name, "value": player.sound_tap},
                        )
                    )
            for name, value in bank_snapshot.items():
                if controller.state.bank.get(name) != value:
                    controller.dispatch(
                        CmdAdminEdit(
                            now_mono=time.monotonic(),
                            edit_type="set_bank",
                            payload={"player": name, "value": value},
                        )
                    )
            persist_setup_config()

        def do_continue(_: ft.ControlEvent) -> None:
            try:
                apply_admin_changes()
                controller.dispatch(CmdPauseOff(now_mono=time.monotonic()))
                show_game()
            except CommandError as exc:
                feedback.value = str(exc)
                page.update()

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
                direction.value = controller.state.order_dir.value
                persist_setup_config()
                show_pause()
            except CommandError as exc:
                feedback.value = str(exc)
                page.update()

        def do_new_game(_: ft.ControlEvent) -> None:
            try:
                apply_admin_changes()
                controller.dispatch(
                    CmdAdminEdit(
                        now_mono=time.monotonic(),
                        edit_type="new_game",
                        payload={"game_id": str(int(time.time()))},
                    )
                )
                persist_setup_config()
                show_game()
            except CommandError as exc:
                feedback.value = str(exc)
                page.update()

        page.add(
            _panel(
                ft.Text("Текущая конфигурация", size=24),
                table,
                ft.Divider(),
                ft.Text(f"Текущий игрок: {controller.state.current_player}"),
                ft.Text(f"Фаза: {controller.state.turn.phase.value}"),
                ft.Text(f"Направление: {controller.state.order_dir.value}"),
                _button("Продолжить", do_continue),
                admin_password,
                _button("Вход в режим админа", do_admin_auth),
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
