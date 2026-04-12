# Этап 15: расширение методов ширины диапазона и сравнение при `recalc`

Документ фиксирует, **что реализовано** в репозитории на этом этапе. Цель: расширить **`width_method`** у монеты так, чтобы **полуширина** рекомендуемого диапазона считалась не только через **ATR**, но и через **стандартное отклонение закрытий**, а также через **ширину канала по high/low** (варианты **donchian** и **historical_range** в MVP на одной формуле), **без перелома** общего потока: центр → полуширина → `low`/`high` → **clamp** по %% от центра → **`RecommendedRange`**.

Связанные документы: [`etap-14.md`](etap-14.md) (методы центра и первая таблица сравнения при `recalc`); [`etap-5.md`](etap-5.md) (базовый `RangeEngine`); [`instrukciya.md`](instrukciya.md) (описание `width_method` и двух таблиц после `recalc`).

**Принцип архитектуры:** расширен только **`RangeEngine`** (расчёт полуширины, минимальное число свечей, сравнение методов ширины при recalc), **`validation`** / **`CoinService.add_coin`**, вывод в **CLI** и **меню**, **`RecalcOutcome`** и **`display_helpers`**. Логика **`Evaluator`**, **`CheckService`**, backtest/optimize по смыслу не менялась; структура **`RecommendedRange`** и JSON по-прежнему хранят строки **`center_method`** / **`width_method`**.

---

## Проблема до этапа

- **`width_method`** поддерживал только **`atr`**: полуширина = **ATR(14) × множитель по `mode`**, как в первом MVP.
- Не было способа задать ширину через **волатильность по close (σ)** или через **размах high/low** окна без дублирования логики вне движка.
- После этапа 14 при **`recalc`** выводилась таблица сравнения **только центров**; сравнить **варианты ширины** при том же центре было нельзя без ручной смены `width_method` в данных.

---

## Цель этапа

1. Добавить **`width_method`**: **`std`**, **`donchian`**, **`historical_range`** рядом с **`atr`**.
2. Ввести явные константы периодов и множителей для **`std`** (отдельно от **`_ATR_MULT`**).
3. Вынести расчёт полуширины в хелперы и диспетчер **`_resolve_half_width`**, не раздувая `calculate_range` монолитом.
4. Разделить требование к длине ряда свечей: **`_min_candles_for_center_only`**, **`_min_candles_for_width_method`**, **`_min_candles_required(cm, wm)`**.
5. Валидировать **`width_method`** при добавлении монеты: **`ALLOWED_WIDTH_METHODS`**, **`validate_width_method`**.
6. При **`recalc`** выводить **вторую таблицу** — сравнение всех методов ширины при фиксированном **`center_method`** монеты (аналогично таблице центров на этапе 14).
7. Обновить help **`range add --width-method`** и **`instrukciya.md`**.
8. Покрыть сценарии **тестами**.

---

## Что сделано

### 1. `RangeEngine`

Файл: **`src/range_program/services/range_engine.py`**.

| Константа / словарь | Назначение (MVP) |
|---------------------|------------------|
| `STD_PERIOD = 20` | Окно закрытий для **σ** |
| `HISTORICAL_RANGE_PERIOD = 20` | Окно свечей для **historical_range** (ширина канала) |
| `DONCHIAN_PERIOD` (уже был) | То же окно для **donchian** (ширина канала) |
| `_STD_MULT` | Множители к **pstdev(close)** по **`mode`**: conservative **3.0**, balanced **2.2**, aggressive **1.6** |
| `_ATR_MULT` | Без изменения смысла для **`atr`** |

**Семантика ширины (полуширина до clamp):**

- **`atr`** — как раньше: **`_atr_wilder` × _ATR_MULT[mode]`**.
- **`std`** — **`pstdev`** по последним **`STD_PERIOD`** закрытиям × **`_STD_MULT[mode]`**.
- **`donchian`** — **`_calculate_half_width_donchian`**: **(max high − min low) / 2** по последним **`DONCHIAN_PERIOD`** свечам; множителей по **`mode`** нет.
- **`historical_range`** — **`_calculate_half_width_historical_range`**: в MVP **та же формула**, что у donchian по окну **`HISTORICAL_RANGE_PERIOD`**; отдельные функции для возможного расхождения позже.

Общий поток: **`center`** → **`_resolve_half_width`** → **`_clamp_half_width`** → **`low`/`high`/`width_pct`**. Ошибки при нулевой/отрицательной ширине канала или нехватке свечей — **`RangeEngineError`**.

**Минимум свечей:** **`_min_candles_required(center_method, width_method) = max(...)`** — учитываются и центр, и ширина (например, для **`price` + `std`** нужно не меньше **20** свечей из-за **std**).

**Сравнение при recalc:**

- **`RECALC_WIDTH_COMPARISON_ORDER`**: **`atr`**, **`std`**, **`donchian`**, **`historical_range`**.
- Метод **`compare_width_methods_for_recalc`**: для каждого `width_method` — **`calculate_range`** с **`replace(coin, width_method=..., capital=None)`** (без расчёта сетки в таблице).

Таблица **центров** (этап 14) уточнена по смыслу: при сравнении центров используется **`width_method` монеты**, а не «все на ATR».

### 2. Модель допустимых значений

Файл: **`src/range_program/models/defaults.py`**.

- **`ALLOWED_WIDTH_METHODS`** — `atr`, `std`, `donchian`, `historical_range`.
- **`DEFAULT_WIDTH_METHOD`** по-прежнему **`atr`**.

Экспорт **`ALLOWED_WIDTH_METHODS`** в **`src/range_program/models/__init__.py`**.

### 3. Валидация

Файл: **`src/range_program/validation.py`**: **`validate_width_method`**.

Файл: **`src/range_program/services/coin_service.py`**: вызов в **`add_coin`** после **`validate_center_method`**.

### 4. `RecalcService` и вывод

Файл: **`src/range_program/services/recalc_service.py`**.

- В **`RecalcOutcome`** добавлено поле **`width_comparison`**.
- После успешного основного расчёта вызываются **`compare_center_methods_for_recalc`** и **`compare_width_methods_for_recalc`**.

Файл: **`src/range_program/display_helpers.py`**: **`print_recalc_width_comparison_table`**; подпись таблицы **center_method** уточнена (фиксированный **`width_method` монеты`).

Файлы: **`src/range_program/cli.py`**, **`src/range_program/menu.py`**: печать обеих таблиц после **`recalc`**; help **`--width-method`**.

### 5. Документация пользователя

Файл: **`docs/instrukciya.md`**: описание **`width_method`**, обновлённая строка про команду **`recalc`** (две таблицы сравнения).

---

## Замечание по интерпретации вывода

- В MVP **`donchian`** и **`historical_range`** для ширины дают **одинаковую** формулу на одном окне — строки в таблице могут совпадать.
- **`std`** после **clamp** по минимальной/максимальной ширине в %% от центра может **совпасть** по итоговым **LOW/HIGH/WIDTH%** с канальными методами, если все попадают в одну и ту же границу clamp — это ожидаемо, а не обязательно ошибка расчёта.

---

## Тесты

- **`tests/test_range_engine.py`**: **`std`**, совпадение **donchian / historical_range** в MVP на синтетике, **`compare_width_methods_for_recalc`**, прежние сценарии центра/ошибок.
- **`tests/test_coin_service.py`**: отклонение недопустимого **`width_method`** при **`add_coin`**.

---

## Что намеренно не входило в этап

- Новые **`center_method`**.
- Изменение **clamp** или **`_MIN_WIDTH_PCT` / `_MAX_WIDTH_PCT`**.
- Разные периоды для **donchian** и **historical_range** по ширине (в MVP совпадают).
- Отдельные колонки «до clamp» в выводе терминала.

---

## Обратная совместимость

- Монеты с **`width_method: atr`** ведут себя как до этапа при тех же данных.
- Разделение минимума свечей по центру и ширине может изменить требование к числу баров для комбинаций вроде **`price` + `std`** (нужно **≥20** свечей вместо **14** только для ATR).

---

## Итог этапа

Программа поддерживает **четыре метода ширины** диапазона в **`RangeEngine`**, проверку при **`add_coin`**, при **`recalc`** — **две таблицы сравнения** (все **center_method** при текущей ширине монеты и все **width_method** при текущем центре монеты), с сохранением в хранилище только **одной** пары настроек монеты и прежней архитектуры вокруг **`RecommendedRange`**.
