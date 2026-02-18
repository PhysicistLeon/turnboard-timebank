# Turnboard Timebank (Flet, Python)

Полноценная реализация **Варианта 2**: event-sourced state machine для Android-first приложения ведущего настольных игр.

## Что реализовано

- Доменная модель (`domain/`) разделена на:
  - `Command` (входные действия)
  - `Event` (факты, пишутся в лог)
  - `Decider` (валидация + генерация событий)
  - `Reducer` (`apply_event`) для чистого восстановления состояния.
- Контроллер (`app/controller.py`) оркестрирует pipeline:
  1. `dispatch(command)`
  2. `decide(...)`
  3. append-only лог
  4. `apply_event(...)`
  5. запуск side effects (звук/вибрация/keep-awake).
- Инфраструктура (`infra/`):
  - `LogWriter` — человекочитаемый лог формата `LOG_FORMAT v=1`
  - `ConfigStore` — ini c паролем (в открытом виде по ТЗ)
  - `SoundRepo`/`EffectSink` — звуки, вибрация, флаг keep-awake.
- UI (`ui/main.py`) на Flet:
  - first-run экран создания пароля
  - Setup экран
  - Game экран с большой кнопкой, таймером и паузой
  - Tech Pause экран с admin-auth, reverse direction, new game
  - авто-пауза на lifecycle pause.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python -m timebank_app
```

## Тесты и качество

```bash
pytest
ruff check .
pylint src/timebank_app
```


## Документация и ТЗ

Полные исходные тексты постановки и архитектурного ТЗ вынесены в `docs/`:

- `docs/product_spec_v1.md` — продуктовая спецификация v1.0 (цели, бизнес-логика, UX, acceptance criteria).
- `docs/architecture_tz_variant2.md` — архитектурное ТЗ по варианту 2 (event-sourced state machine, риски, тест-стратегия).
- `docs/IMPLEMENTATION_CONTEXT.md` — быстрый контекст для разработчика/агента, чтобы быстрее возвращаться к деталям реализации.

## Примечания по реализации

- Источник истины времени — `now_mono` из команд; UI-частота не влияет на списание.
- `cooldown` не списывает банк; `warn_every` считается только в `countdown`.
- Все важные шаги формируются как события и пишутся в единый лог-файл.
- После старта партии `ADMIN_EDIT` требует включённого admin mode.
- `TURN_UNDO` реализован через восстановление данных последнего `TURN_END`.

## Структура проекта

```text
src/timebank_app/
  app/controller.py
  domain/{commands,events,engine,models}.py
  infra/{effects,logging,storage}.py
  ui/main.py
tests/
```
