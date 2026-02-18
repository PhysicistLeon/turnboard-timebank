# ТЗ по архитектуре и инженерная декомпозиция (Variant 2)

## A. Перевод постановки в инженерные термины
### A1. Функциональные требования
**Основной сценарий (игровой экран):**
1. Экран “Игра” с **большой кнопкой**:
   - отображает `name текущего игрока`
   - отображает обратный отсчёт **банка** текущего игрока
   - нажатие:
     - проигрывает звук текущего игрока (`sound_tap`)
     - вибрация устройства
     - завершает ход текущего игрока и переключает ход на следующего
2. У каждого игрока есть **банк времени на всю партию**.
3. В начале каждого хода у игрока есть **cooldown**.
4. **Предупреждение о длинном ходе** после cooldown каждые `warn_every` секунд.
5. “Мигание” кнопки:
   - линейное колебание от чёрного к цвету игрока и обратно
   - частота меняется плавно от `1/60 Гц` к `1 Гц`.
6. Кнопка **TECH PAUSE**:
   - ставит ход на паузу без смены игрока
   - открывает экран настроек.

**Экран “Настройки/Пауза”:**
7. В паузе показывается:
- список игроков в порядке очереди
- остаток банка у каждого
- настройки партии (`bank initial`, cooldown, warn_every, направление)
8. Во время паузы доступны:
   - **Continue**
   - **New Game**
   - **Undo turn** (админ)
   - **Reverse order direction** (админ)
   - **Reorder players** и другие правки.

**Доступ к звукам:**
9. Выбор звуков из внешней папки только на чтение.
10. Есть предпрослушивание.

**Администрирование и пароль:**
11. До старта игры изменения — обычные.
12. После старта любые изменения `player/rules/order` — административные, требуют пароль.
13. Пароль задаётся при первом запуске и хранится в ini в открытом виде.

**Логирование:**
14. Одна строка на событие: timestamp, тип, параметры.
15. Лог человекочитаемый.
16. Логируются передачи хода, паузы, админ-изменения, background/call.
17. По логу возможно восстановление поведения.

**Android-специфика:**
18. Android-only.
19. Экран не гаснет во время игры.
20. background/call → auto tech pause.
21. Ориентация фиксирована.

### A2. Непрямые требования (инварианты/edge-cases)
**Инварианты:**
- I1: в RUNNING всегда один `current`.
- I2: TECH_PAUSE не меняет `current/order/dir`.
- I3: следующий игрок вычисляется по `order` и `dir` на момент передачи.
- I4: после reorder next считается по **новому** порядку.
- I5: источник истины времени — монотонные дельты.
- I6: любое admin-действие после GAME_START должно попасть в лог с old/new.

**Edge-cases:**
- E1: rename игрока должен логировать old/new.
- E2: reorder не должен терять current.
- E3: background в любой фазе должен фиксировать phase/cooldown.
- E4: warn должен быть детерминирован при паузах/undo.
- E5: New Game создаёт новый `game_id` в общем логе.
- E6: звук может стать недоступен — fallback без падения.

### A3. Не-цели
- iOS/desktop.
- Фоновая работа таймера.
- Безопасное хранение пароля.
- Анти-читинг по системному времени.
- Обязательный машиночитаемый экспорт.

---
## B. Варианты реализации
### Вариант 1: минимальный
Монолитный контроллер + UI-тик таймер.

### Вариант 2: рекомендуемый (event-sourced state machine)
- Чёткая машина состояний (SETUP/RUNNING/TECH_PAUSE).
- Команды → валидация → доменные события.
- События:
  - применяются к `GameState` (pure reducer),
  - пишутся в лог,
  - запускают эффекты (звук/вибро/keep-awake).
- Тайм-логика через монотонное время.
- Undo как доменное событие.

### Вариант 3: расширяемый
Variant 2 + plugin rules + storage migrations + observability.

---
## C. Рекомендуемый вариант
Выбран **Вариант 2** как баланс скорости и качества:
- детерминизм,
- реплей,
- тестируемость,
- меньше связности UI↔домен↔I/O.

---
## D. Приземление в код
### D1. Слои
1. `ui/`
2. `domain/` (model/commands/events/reducer/validator)
3. `app/` (controller/orchestrator)
4. `infra/` (log, sound, vibration, keep-awake, storage, lifecycle)

### D2. Контракты
- `Reducer.apply(state, event) -> state`
- `Decider.decide(state, command) -> [event] | error`
- `GameController.dispatch(command)`
- `Clock.now_monotonic()` + `Clock.now_wall()`

### D3. Схемы команд/событий
**Commands (пример):**
- `CmdStartGame`
- `CmdTap`
- `CmdTechPauseOn/Off`
- `CmdAdminAuth`
- `CmdAdminEdit`
- `CmdUndo`
- `CmdOrderReverse`
- `CmdAppBackground/Resume`
- `CmdNewGame`

**Events (минимум):**
- `APP_START`
- `APP_BACKGROUND`
- `APP_RESUME`
- `GAME_START`
- `TURN_START`
- `COOLDOWN_START`
- `COOLDOWN_END`
- `WARN_LONG_TURN`
- `TURN_END`
- `TECH_PAUSE_ON/OFF`
- `ADMIN_AUTH_OK/FAIL`
- `ADMIN_MODE_ON/OFF`
- `SETUP_EDIT`
- `ADMIN_EDIT`
- `TURN_UNDO`
- `ORDER_REVERSE`
- `NEW_GAME`
- `GAME_END`

Формат строки лога:
```text
<TS> <SEQ> G=<id> <EVENT> k1=v1 k2=v2 ... -- comment
```

### D4. Псевдокод
Контроллер:
```pseudo
dispatch(cmd):
  now_mono = clock.now_monotonic()
  now_wall = clock.now_wall()
  result = decider.decide(state, cmd, now_mono)
  if error: return
  for ev in events:
    log.append(format(ev, now_wall, seq++, game_id))
    state = reducer.apply(state, ev)
  effects_runner.run(effect_planner.from(events, state))
  ui.render(state)
```

Tap:
```pseudo
decide_tap(state, now):
  require state.mode == RUNNING
  state2 = state.with_updated_time(now)
  ev1 = TURN_END(...)
  next = compute_next(order, dir, current)
  ev2 = TURN_START(next)
  ev3 = COOLDOWN_START(next)
  return [ev1, ev2, ev3]
```

---
## E. Влияние на кодовую базу
### E1. Тест-стратегия
- Unit: reducer + decider.
- Integration: controller + infra.
- Contract: golden tests для формата лога.

### E2. Наблюдаемость
- Основной артефакт: общий лог.
- Ошибки I/O через `ERROR ...` события.

### E3. Миграции
- `LOG_FORMAT v=1`
- `config_version=1`

### E4. Сложности поддержки
- Нужна дисциплина по событиям/tests.

---
## F. Риски и долги
### F1. Топ-риски
1. Android storage к внешней папке звуков.
2. Точность таймера при лагах UI.
3. Имя как идентификатор.
4. Невозможность писать лог.
5. Тяжёлая анимация/CPU.

### F2. Осознанные долги
- Пароль в ini открытым текстом.
- Один общий лог без ротации.

### F3. Стресс-сценарии
- S1: фриз приложения на 5–10 сек.
- S2: reorder + reverse + undo в паузе.

---
## G. Итоговая проверка
Чеклист покрытия требований:
- [x] большая кнопка/таймер/tap-сценарий
- [x] банк + cooldown + warn_every
- [x] tech pause manual/auto
- [x] admin-правки под паролем
- [x] лог событий + изменения очереди
- [x] ориентация/keep-awake/Android-only

---
## TL;DR
- Архитектура: **state machine + commands/events + append-only log**.
- Источник времени: **монотонные метки**, не UI-тик.
- Админ-изменения после старта: только через `ADMIN_*` под паролем.
- Основные риски: storage/logging/timer/name-id; закрываются валидацией, fallback и тестами.
