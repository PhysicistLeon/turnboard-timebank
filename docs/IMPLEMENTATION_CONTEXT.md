# Implementation Context (agent quick reference)

Короткий контекст для быстрого возврата к проекту.

## Текущее состояние
- Архитектура: Variant 2 (event-sourced).
- Язык/стек: Python + Flet.
- Целевые версии рантайма:
  - Flet: `0.80.5`
  - Flutter: `3.38.7`
  - Pyodide: `0.27.7`
- Главные модули:
  - `src/timebank_app/domain/` — модели, команды, события, decider/reducer.
  - `src/timebank_app/app/controller.py` — оркестрация `decide -> log -> apply -> effects`.
  - `src/timebank_app/infra/` — ini-конфиг игры, лог, эффекты/звуки.
  - `src/timebank_app/ui/main.py` — экраны Setup/Game/Tech Pause.

## Ключевые ограничения из ТЗ
- После `GAME_START` любые изменения настроек только в `admin_mode`.
- `cooldown` не списывает банк.
- `warn_every` только после `cooldown`.
- `background` должен ставить в tech pause без смены current.
- `TURN_UNDO` восстанавливает last `TURN_END`.
- UI-таймер должен отображаться строго в формате `MM:SS`; при перерасходе времени — `-MM:SS`.

## Быстрые команды проверки
```bash
ruff check .
python -m pytest -q
python -m pylint src/timebank_app
```

## Что уже болело
- В разных версиях Flet различаются `run/app`, `Button/ElevatedButton`, lifecycle enum.
- Добавлены совместимые обёртки в `ui/main.py`:
  - `run_flet_app()`
  - `_button(...)`
  - `_is_background_lifecycle_state(...)`

## Документы
- Полный продуктовый spec: `docs/product_spec_v1.md`
- Полное архитектурное ТЗ: `docs/architecture_tz_variant2.md`
