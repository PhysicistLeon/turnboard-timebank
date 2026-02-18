# Implementation Context (agent quick reference)

Короткий контекст для быстрого возврата к проекту.

## Текущее состояние
- Архитектура: Variant 2 (event-sourced).
- Язык/стек: Python + Flet.
- Главные модули:
  - `src/timebank_app/domain/` — модели, команды, события, decider/reducer.
  - `src/timebank_app/app/controller.py` — оркестрация `decide -> log -> apply -> effects`.
  - `src/timebank_app/infra/` — ini, лог, эффекты/звуки.
  - `src/timebank_app/ui/main.py` — экраны Setup/Game/Tech Pause.

## Ключевые ограничения из ТЗ
- После `GAME_START` любые изменения настроек только в `admin_mode`.
- `cooldown` не списывает банк.
- `warn_every` только после `cooldown`.
- `background` должен ставить в tech pause без смены current.
- `TURN_UNDO` восстанавливает last `TURN_END`.

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


## Целевой runtime-контекст
- Flet: 0.80.5
- Flutter: 3.38.7
- Pyodide: 0.27.7

## Обновлённый продуктовый приоритет
- Таймер UI всегда отображается строго в формате `MM:SS`.
- При перерасходе времени формат остаётся `-MM:SS` (для 100+ минут — `MMM:SS`, `MMMM:SS` и т.д.).
