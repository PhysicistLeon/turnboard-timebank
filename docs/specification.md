# Спецификация мобильного приложения **(Android-only) на Godot 4**

Версия: v1.0 (implementation guide)
Движок: **Godot Engine 4.6.x (stable)** ([Godot Engine documentation][1])
Цель документа: дать разработчику **самодостаточное руководство к реализации** (UI/UX + доменная логика + инженерная архитектура + Android-особенности Godot 4).

---

## 1) Назначение и сценарий использования

Приложение — «таймер ведущего» для настольных игр:

* у каждого игрока есть **банк времени на всю партию**;
* передача хода происходит **одним нажатием** на большую кнопку;
* поддерживаются **тех.паузы** (ручные и автоматические при background/call);
* после старта партии изменения — **админские**, под паролем;
* всё значимое пишется в **append-only человекочитаемый лог**, одна строка на событие;
* работает **только на Android**, ориентация фиксирована, в режиме игры экран не гаснет.

Не-цели (осознанно):

* iOS/desktop;
* «фоновые таймеры» при выгрузке приложения ОС;
* защищённое хранение пароля (пароль в ini открытым текстом);
* анти-читинг по системному времени.

---

## 2) Платформенные опоры Godot 4 (обязательные правила реализации)

### 2.1 Источник времени

* Для игровой логики используем **монотонное** время `Time.get_ticks_msec()` (или usec). Оно гарантированно не уменьшается и подходит для точных дельт. ([Godot Engine documentation][2])
* Для timestamp в логе используем `_from_system` методы (wall-clock), но **не** для расчётов. ([Godot Engine documentation][2])

### 2.2 Keep screen on

В режиме RUNNING: `DisplayServer.screen_set_keep_on(true)`, иначе `false`. ([Godot Engine documentation][3])

### 2.3 Android lifecycle → auto tech pause

Перехватываем `MainLoop.NOTIFICATION_APPLICATION_PAUSED` и `...RESUMED` и маппим на команды домена (background/resume). ([Godot Engine documentation][4])
Важно: на мобильных платформах «последний шанс сохранить состояние» — именно при PAUSED. ([Godot Engine documentation][5])

### 2.4 Вибрация

`Input.vibrate_handheld(duration_ms, amplitude)`; на Android нужно включить permission **VIBRATE** в export preset, иначе функция может не работать/быть проблемной. ([Godot Engine documentation][6])

### 2.5 Внешние звуки: Storage Access Framework (SAF)

Выбор папки/файлов делаем через `DisplayServer.file_dialog_show(...)`. На Android возвращается **URI**, а не путь. URI можно передать прямо в `FileAccess`. Для папки (OPEN_DIR) возвращается **tree URI**; доступ к файлам внутри: `treeUri#relative/path/to/file`. Также можно закрепить доступ через `AndroidRuntime.updatePersistableUriPermission(uri, true)`. ([Godot Engine documentation][7])

---

## 3) Термины и модель данных

### 3.1 Player

* `name: String` — уникально в рамках партии (используется как идентификатор в логах).
* `color: Color` — цвет игрока.
* `sound_tap: String` — идентификатор выбранного звука (имя/relative path в выбранной папке или URI-ключ).
* (опционально) `sound_warn: String` — если делаете per-player warn, иначе общий `rules.warn_sound`.

### 3.2 Rules

* `bank_initial_ms: int` — начальный банк (миллисекунды).
* `cooldown_ms: int` — «разогрев» (банк не уменьшается).
* `warn_every_ms: int` — период предупреждений после cooldown.
* `warn_sound: String` — общий звук предупреждения (если не per-player).
* `blink_min_hz = 1/60`, `blink_max_hz = 1` — диапазон частоты пульсации.

### 3.3 Game session

* `game_id: String` — уникальный идентификатор сессии (например, ISO timestamp).
* `order: Array[String]` — список имён игроков (очередность).
* `order_dir: enum {CW, CCW}`
* `bank_ms: Dictionary[name -> int]` — остатки банка (мс), допускается отрицательное.
* `current: String` — текущий игрок (обязателен в RUNNING/TECH_PAUSE).
* `phase: enum {SETUP, RUNNING, TECH_PAUSE}`
* `turn_subphase: enum {COOLDOWN, COUNTDOWN}` (актуально в RUNNING/TECH_PAUSE)
* `subphase_remaining_ms` (для COOLDOWN, если хотите хранить явно) или производно.
* `elapsed_no_cooldown_ms` — «чистое» время хода без cooldown (для warn и undo).
* `admin_mode: bool` — true только в TECH_PAUSE после успешного пароля.

---

## 4) Состояния приложения и инварианты

### 4.1 Машина состояний

* **SETUP**: до старта партии, любые правки без пароля.
* **RUNNING**: активен ход текущего игрока (COOLDOWN или COUNTDOWN).
* **TECH_PAUSE**: время заморожено, текущий игрок не меняется, доступен экран настроек.

### 4.2 Инварианты (обязательная проверка в домене)

* I1: в RUNNING всегда ровно один `current`.
* I2: TECH_PAUSE не меняет `current/order/order_dir`.
* I3: следующий игрок вычисляется по `order` + `order_dir` в момент передачи.
* I4: после reorder следующий считается по **новому** порядку.
* I5: расчёт времени — только через монотонные дельты (`Time.get_ticks_msec`). ([Godot Engine documentation][2])
* I6: любое admin-действие после GAME_START логирует old/new.

---

## 5) Функциональные требования по экранам

## 5.1 Первый запуск: создание пароля

Если конфиг отсутствует или пароль не задан:

1. показать экран создания пароля (2 поля: password/confirm);
2. сохранить пароль в `user://config.ini` в открытом виде;
3. перейти в SETUP.

Хранилище ini: `ConfigFile` (INI-формат). ([Godot Engine documentation][8])
Файлы приложения — в `user://`. ([Godot Engine documentation][9])

---

## 5.2 Экран SETUP (до старта партии)

UI:

* список игроков в порядке `order`:

  * имя, цвет, выбранный sound_tap,
  * отображение `bank_initial` как «стартовый банк».
* управление:

  * add/remove player;
  * reorder (кнопки вверх/вниз или drag&drop);
  * rename, смена цвета, выбор звука (с предпрослушиванием);
* блок правил:

  * bank_initial, cooldown, warn_every, warn_sound, направление (CW/CCW);
* кнопка **Start Game**.

Валидации:

* имена уникальны (ошибка/подсветка при конфликте);
* значения времени неотрицательные, warn_every > 0;
* если звуки не выбраны/недоступны — это допустимо (silent fallback).

---

## 5.3 Экран GAME (RUNNING)

Главный элемент: **большая кнопка** на почти весь экран:

* показывает `name` текущего игрока;
* показывает таймер банка в формате **MM:SS** или **-MM:SS** (если ушли в минус);
* при нажатии:

  1. проигрывает `sound_tap` текущего игрока (если доступен);
  2. делает вибрацию устройства;
  3. завершает ход и переключает на следующего (с новым cooldown).

Доп. элементы:

* кнопка **TECH PAUSE**:

  * ставит игру на паузу **без смены игрока**;
  * открывает экран TECH_PAUSE/Settings.
* (опционально) индикатор направления очереди.

Пульсация кнопки:

* линейное колебание от чёрного к цвету игрока и обратно;
* частота плавно растёт от 1/60 Гц к 1 Гц по мере приближения банка к 0.

Системное:

* в RUNNING экран не гаснет (`screen_set_keep_on(true)`). ([Godot Engine documentation][3])

---

## 5.4 Экран TECH_PAUSE / Settings

Показывает:

* список игроков в текущем порядке:

  * имя, цвет, остаток банка (MM:SS/-MM:SS), звуки;
* блок текущего состояния:

  * current, subphase (cooldown/countdown),
  * cooldown remaining (если релевантно),
  * направление очереди,
  * elapsed_no_cooldown (для диагностики — опционально).
    Кнопки:
* **Continue** (возврат в RUNNING без смены игрока);
* **New Game** (новый game_id, банки сбросить, конфиг сохранить);
* **Admin mode** → ввод пароля;
* в admin mode доступны:

  * **Undo last turn**
  * **Reverse order direction**
  * **Reorder players**
  * правки игроков/банков/правил.

После Continue рекомендуется auto-exit admin mode (или явная кнопка Exit).

---

## 6) Доменная логика (детерминированная)

### 6.1 Представление времени и формат UI

* Внутри: миллисекунды (int).
* На UI: всегда **MM:SS** / **-MM:SS**, округление: показываем floor секунд по модулю; знак отдельно.
* В лог: можно писать ms или сек (но единообразно и явно, например `bank_after_ms=...`).

### 6.2 Ход игрока: cooldown → countdown

При `TURN_START(player)`:

* устанавливаем `turn_subphase = COOLDOWN`;
* фиксируем `turn_started_mono_ms = now`;
* `elapsed_no_cooldown_ms = 0`.

В COOLDOWN:

* банк не уменьшается;
* warn не считается.

По истечении `cooldown_ms`:

* `COOLDOWN_END`;
* `turn_subphase = COUNTDOWN`;
* обновляем базовые метки так, чтобы дальнейшая дельта списывалась корректно.

### 6.3 Countdown: списание банка

В COUNTDOWN:

* при любом «пересчёте» (render tick / команда / resume) вычисляем:

  * `delta = now_mono - last_mono`
  * `bank_ms[current] -= delta`
  * `elapsed_no_cooldown_ms += delta`
  * `last_mono = now_mono`

### 6.4 Предупреждения warn_every (после cooldown)

* Warn срабатывает каждый раз, когда `elapsed_no_cooldown_ms` пересекает кратное `warn_every_ms`.
* Требование: детерминизм при паузах/фризах:

  * если приложение «подвисло» и delta большая, возможны несколько warn за один пересчёт — это нормально, но **количество и моменты должны быть воспроизводимы по логу** (см. ниже).

### 6.5 Tap → передача хода

Команда: `CmdTap` (доступна только в RUNNING)

1. домен обновляет время до now_mono (если COUNTDOWN);
2. создаёт `TURN_END` для current с параметрами:

   * `name`
   * `bank_after_ms`
   * `spent_no_cooldown_ms` (ключ для undo)
   * `was_in_cooldown` (для прозрачности)
3. вычисляет `next` по `order` и `order_dir`;
4. создаёт `TURN_START(next)` + `COOLDOWN_START(next)`.

Эффекты:

* звук tap (если доступен),
* вибрация.

### 6.6 TECH_PAUSE (manual/auto)

Команды:

* `CmdTechPauseOn(reason)` — доступна в RUNNING и idempotent
* `CmdTechPauseOff` — доступна в TECH_PAUSE

При входе в TECH_PAUSE:

* домен сначала «догоняет» время до now_mono (если COUNTDOWN), затем **замораживает**:

  * фиксируем остатки cooldown/countdown и `last_mono`;
* банк больше не уменьшается;
* warn не проигрываются.

Auto pause:

* при `NOTIFICATION_APPLICATION_PAUSED` всегда `CmdTechPauseOn(reason="app_paused")`. ([Godot Engine documentation][4])
  При resume:
* `CmdAppResume` или `CmdTechPauseOn(reason="app_resumed_hold")` (политика: **после возврата остаёмся в паузе до Continue**).

### 6.7 Admin mode и пароль

* До `GAME_START`: правки идут как `SETUP_EDIT`.
* После `GAME_START`: правки только если `admin_mode=true`, иначе reject.
* `CmdAdminAuth(password)`:

  * сравнить с сохранённым в config.ini;
  * события: `ADMIN_AUTH_OK/FAIL`, затем `ADMIN_MODE_ON`.

Пароль хранится открытым текстом (не-цель: безопасность).

### 6.8 Reorder players (после старта)

Требование: reorder не теряет current.

* Если current остаётся в списке — сохраняем current.
* Следующий игрок после current вычисляется уже по **новому** order при следующем tap.

Логировать: `ADMIN_EDIT type=reorder old="A,B,C" new="B,A,C"`.

### 6.9 Reverse order direction

* current не меняется.
* следующий игрок при следующем tap будет по новому direction.
  Логировать: `ORDER_REVERSE old_dir=... new_dir=...`.

### 6.10 Undo last turn (админ)

Политика фиксирована:

* undo ссылается на **последний TURN_END**;
* после undo активным снова становится `TURN_END.name`;
* банк игрока восстанавливается в `TURN_END.bank_after_ms`;
* subphase становится **COUNTDOWN** (не cooldown);
* `elapsed_no_cooldown_ms` восстанавливаем так, чтобы warn продолжились корректно:

  * минимальный детерминированный вариант: хранить в TURN_END `spent_no_cooldown_ms` и откатить его на игрока.

Логировать: `TURN_UNDO target_seq=... restored_player=...`.

### 6.11 New Game

* создаётся новый `game_id`;
* банки всех игроков = `rules.bank_initial_ms`;
* конфиг (игроки/порядок/правила) сохраняется;
* лог продолжается в том же файле, но с новым `G=<game_id>`.

---

## 7) Логирование (append-only, одна строка на событие)

### 7.1 Формат строки

```
<TS_ISO> <SEQ> G=<game_id> <EVENT> k1=v1 k2=v2 ... -- comment
```

Минимум:

* `TS_ISO` (wall-clock),
* `SEQ` монотонный (int),
* `G=` id партии,
* `EVENT`,
* параметры key=value.

### 7.2 Что обязательно логировать

* `APP_START`, `APP_BACKGROUND`, `APP_RESUME`
* `GAME_START` (полный order, rules)
* `TURN_START`, `TURN_END` (и spent_no_cooldown_ms)
* `COOLDOWN_START/END`
* `WARN_LONG_TURN`
* `TECH_PAUSE_ON/OFF` + reason
* `ADMIN_AUTH_OK/FAIL`, `ADMIN_EDIT` (old/new)
* `ORDER_REVERSE`, `TURN_UNDO`, `NEW_GAME`
* любые ошибки I/O: `ERROR ...`

### 7.3 Реализация записи в файл (Godot 4)

* Файл: `user://logs/events.log`. Пути `user://` описаны в документации. ([Godot Engine documentation][9])
* Для append: открываем файл, делаем `seek_end()` и затем `store_line()`. `store_line()` в режимах WRITE может перезаписать файл, поэтому `seek_end()` обязателен. ([Godot Engine documentation][10])

---

## 8) UI/UX детали под Godot 4

### 8.1 Общие принципы

* максимальная читаемость: крупные шрифты, высокий контраст;
* минимум действий: «один тап — один ход»;
* UI не содержит бизнес-логики: только отображение state и отправка команд.

### 8.2 Пульсация (blink)

Реализация:

* визуальная анимация через Tween/AnimationPlayer;
* цвет: `lerp(Color.BLACK, player_color, wave)` где `wave` идёт 0→1→0;
* частота: `hz = lerp(blink_min_hz, blink_max_hz, f(progress))`,

  * `progress = clamp(bank_ms / bank_initial_ms, 0..1)` (для отрицательных — 0),
  * `f` — монотонная, плавная (например, `1 - progress` или ease).

Требование: анимация не влияет на таймер (таймер только из домена).

### 8.3 Формат таймера

* `MM:SS`, `-MM:SS` при перерасходе.
* Смена минут/сек — строго от доменного `bank_ms`.

---

## 9) Архитектура реализации (рекомендуемая)

### 9.1 Слои и ответственность

**domain/** (pure, тестируемый)

* модели: GameState/Player/Rules
* команды/события (минимум структуры)
* `Decider.decide(state, cmd, now_mono)` → events|error
* `Reducer.apply(state, event)` → new_state
* time math (cooldown/warn thresholds)

**app/** (оркестрация)

* `GameController` (dispatch pipeline)
* `EffectPlanner` (какие эффекты из каких событий)
* `Replay` (опционально: восстановление по логу)

**infra/** (I/O и платформа)

* Clock (`Time.get_ticks_msec`, wall-time) ([Godot Engine documentation][2])
* Logger (`FileAccess`, seek_end, store_line) ([Godot Engine documentation][10])
* SoundService (SAF URI + runtime loading аудио)
* Haptics (`Input.vibrate_handheld`) ([Godot Engine documentation][6])
* KeepAwake (`DisplayServer.screen_set_keep_on`) ([Godot Engine documentation][3])
* Lifecycle (notifications paused/resumed) ([Godot Engine documentation][4])
* Storage (ConfigFile ini) ([Godot Engine documentation][8])

**ui/** (Godot сцены)

* PasswordSetup / Setup / Game / PauseSettings

### 9.2 Pipeline dispatch (обязательная дисциплина)

1. `now_mono = Clock.now_monotonic_ms()`
2. `now_wall = Clock.now_wall_iso()`
3. `events = Decider.decide(state, cmd, now_mono)` (или reject)
4. для каждого события:

   * логируем строку (append),
   * `state = Reducer.apply(state, event)`
5. выполняем эффекты (звук/вибро/keepawake/навигация)
6. обновляем UI (рендер от state)

---

## 10) Реализация звука (внешняя папка, read-only)

### 10.1 Выбор источника звуков

* В Settings добавить кнопку: **Select sounds folder**
* Вызов `DisplayServer.file_dialog_show(..., mode=FILE_DIALOG_MODE_OPEN_DIR, ...)`
* Сохраняем `treeUri` в config.
* Берём persistable permission:

  * `Engine.get_singleton("AndroidRuntime").updatePersistableUriPermission(treeUri, true)` ([Godot Engine documentation][7])

### 10.2 Идентификаторы звуков

Храним не абсолютные пути, а:

* `sound_tap = "tap1.mp3"` (relative filename)
* реальный доступ: `treeUri + "#" + sound_tap`

### 10.3 Runtime загрузка

* MP3: `AudioStreamMP3.load_from_file(uri_or_tree_path)` ([Godot Engine documentation][11])
* OGG: `AudioStreamOggVorbis.load_from_file(...)` ([Godot Engine documentation][12])
* Проигрывание: `AudioStreamPlayer` (1 общий плеер достаточно).

Fallback:

* если файл недоступен/ошибка decode:

  * не падать, просто silent,
  * `ERROR sound_unavailable file=...` в лог.

---

## 11) Android export / Project settings (чеклист)

### 11.1 Export preset (Android)

* Permissions:

  * включить **VIBRATE** (если используете вибрацию). ([Godot Engine documentation][6])
* Target API/SDK — актуальный по вашей CI (не часть домена).
* Orientation:

  * фиксировать в Project Settings (handheld orientation) и/или через DisplayServer API.

### 11.2 Project Settings

* Ориентация: `display/window/handheld/orientation` (фиксированная).
* Убедиться, что UI масштабируется под выбранный viewport.

---

## 12) Ошибки и устойчивость

Обязательные сценарии:

* **лог не пишется** (нет места/ошибка доступа):

  * приложение не должно падать;
  * показываем ненавязчивый баннер в TECH_PAUSE (опционально);
  * доменно фиксируем `ERROR log_write_failed`.
* **SAF доступ потерян** (папку переименовали/удалили):

  * silent fallback;
  * `ERROR sound_unavailable`;
  * в Settings показать «Источник звуков недоступен, выберите заново».
* **фризы 5–10 секунд**:

  * при следующем пересчёте time delta большая — корректно списываем банк и корректно генерим warn (возможно несколько).

---

## 13) Тестирование и критерии готовности

### 13.1 Unit (domain)

* Reducer/Decider:

  * переходы фаз, инварианты;
  * cooldown не списывает банк;
  * warn срабатывает детерминированно на кратных warn_every;
  * reorder не теряет current;
  * reverse влияет на next;
  * undo восстанавливает bank и elapsed_no_cooldown;
  * new game создаёт новый game_id и сбрасывает банки.

### 13.2 Integration (app/infra)

* Logger append (seek_end);
* SAF: выбор папки → persist permission → чтение файла;
* Lifecycle: PAUSED → TECH_PAUSE_ON; RESUMED → остаёмся в паузе до Continue.

### 13.3 Golden tests (лог)

* фиксируем эталонный формат строк и сравниваем.

### 13.4 Acceptance criteria (итог)

1. пароль создаётся при первом запуске и сохраняется в ini;
2. в SETUP можно настроить игроков/порядок/правила и стартовать;
3. в RUNNING:

   * большая кнопка показывает имя+MM:SS, пульсирует,
   * tap → звук(если есть)+вибро+переключение,
   * cooldown не списывает банк,
   * warn срабатывает каждые N секунд после cooldown;
4. TECH PAUSE останавливает время без смены игрока;
5. background/call → auto tech pause;
6. после GAME_START правки только в admin mode (под паролем) и логируются old/new;
7. reorder меняет «следующего» относительно current по новому порядку;
8. reverse direction работает и логируется;
9. undo соответствует политике и детерминирован по логу;
10. new game создаёт новый game_id и сбрасывает банки;
11. лог содержит стартовые правила/очередь и все ключевые события.

---

## 14) Рекомендуемая структура проекта (практический шаблон)

```
/autoload
  GameController.gd
  Services.gd
/domain
  model/*.gd
  commands/*.gd
  events/*.gd
  Decider.gd
  Reducer.gd
  TimeMath.gd
/infra
  Clock.gd
  Logger.gd
  Storage.gd
  Lifecycle.gd
  KeepAwake.gd
  Haptics.gd
  SoundService.gd
/ui
  PasswordSetup.tscn (+.gd)
  Setup.tscn (+.gd)
  Game.tscn (+.gd)
  PauseSettings.tscn (+.gd)
/logs (runtime in user://logs)
```

---



[1]: https://docs.godotengine.org/?utm_source=chatgpt.com "Godot Docs – 4.6 branch — Godot Engine (stable ..."
[2]: https://docs.godotengine.org/en/stable/classes/class_time.html?utm_source=chatgpt.com "Time — Godot Engine (stable) documentation in English"
[3]: https://docs.godotengine.org/en/stable/classes/class_displayserver.html?utm_source=chatgpt.com "DisplayServer - Godot Docs"
[4]: https://docs.godotengine.org/en/4.5/classes/class_mainloop.html?utm_source=chatgpt.com "MainLoop — Godot Engine (4.5) documentation in English"
[5]: https://docs.godotengine.org/en/latest/tutorials/inputs/handling_quit_requests.html?utm_source=chatgpt.com "Handling quit requests - Godot Docs"
[6]: https://docs.godotengine.org/en/4.4/classes/class_input.html?utm_source=chatgpt.com "Input — Godot Engine (4.4) documentation in English"
[7]: https://docs.godotengine.org/en/stable/classes/class_displayserver.html "DisplayServer — Godot Engine (stable) documentation in English"
[8]: https://docs.godotengine.org/en/4.4/classes/class_configfile.html?utm_source=chatgpt.com "ConfigFile — Godot Engine (4.4) documentation in English"
[9]: https://docs.godotengine.org/en/latest/tutorials/io/data_paths.html?utm_source=chatgpt.com "File paths in Godot projects"
[10]: https://docs.godotengine.org/en/stable/classes/class_fileaccess.html?utm_source=chatgpt.com "FileAccess — Godot Engine (stable) documentation in English"
[11]: https://docs.godotengine.org/en/4.4/classes/class_audiostreammp3.html?utm_source=chatgpt.com "AudioStreamMP3 - Godot Docs"
[12]: https://docs.godotengine.org/en/stable/classes/class_audiostreamoggvorbis.html "AudioStreamOggVorbis — Godot Engine (stable) documentation in English"
