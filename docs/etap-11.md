# Этап 11: капитал по монете и варианты геометрической сетки

Документ фиксирует, **что реально сделано** на этом этапе в репозитории Range Program. Цель этапа: **второй слой поверх уже рассчитанного `recommended_range`** — при заданном **капитале** на монету автоматически предлагать **три варианта** геометрической сетки (плотная / средняя / редкая), с **числом уровней**, **шагом в %** и **размером ордера**, **без** изменения алгоритма ATR/EMA диапазона, **без** учёта комиссий и минимального лота биржи, **без** автоторговли.

Связанные документы: [`plan.md`](plan.md); этап 5 (рекомендуемый диапазон и `recalc`) — [`etap-5.md`](etap-5.md); этап 10 (сравнение режимов **диапазона**) — [`etap-10.md`](etap-10.md).

---

## Важное различие терминов

- **`coin.mode`** (**`conservative` / `balanced` / `aggressive`**) — по-прежнему относится к **ширине диапазона** в **`RangeEngine`** (множители ATR и clamp по %).
- **`GridConfig.mode`** с теми же именами — это **профили сетки по плотности**: **aggressive** = больше уровней и меньший шаг %; **conservative** = меньше уровней и больший шаг %. Это **не** дублирование одного смысла.

---

## Цель этапа

1. Поле **`Coin.capital: float | None`** — планируемый капитал в котируемом активе (по умолчанию в UI/CLI — **`DEFAULT_QUOTE_ASSET`**, например USDT).
2. Модель **`GridConfig`** и поле **`RecommendedRange.grid_configs`** — сохраняются в **`data/coins.json`** вместе с **`recommended_range`** после **`recalc`**.
3. Расчёт сетки в **`RangeEngine`** (функция **`compute_geometric_grid_configs`**) после вычисления **`width_pct`**.
4. CLI: **`--capital`** у **`add`**, **`set-capital`**, **`clear-capital`**, обновлённые **`recalc`**, **`show`**, **`list`**.

---

## Что сделано

### 1. Модель `GridConfig`

Файл: **`src/range_program/models/grid_config.py`**.

Поля: **`mode`** (`aggressive` | `balanced` | `conservative` в смысле **сетки**), **`grid_count`**, **`step_pct`**, **`order_size`**.

### 2. Расширение `RecommendedRange`

Файл: **`src/range_program/models/recommended_range.py`**.

- **`grid_configs: tuple[GridConfig, ...]`** — по умолчанию пустой кортеж.
- Если **`capital`** не задан или расчёт сетки не выполнялся — **`grid_configs`** пустой; старые JSON без ключа **`grid_configs`** при чтении дают пустой список.

### 3. Модель `Coin`

Файл: **`src/range_program/models/coin.py`**.

- **`capital: float | None = None`** — в **`Coin.create`** опционально.

### 4. Логика в `RangeEngine`

Файл: **`src/range_program/services/range_engine.py`**.

- Фиксированные **шаги** по профилям сетки: **0.5%**, **0.8%**, **1.4%** (для aggressive / balanced / conservative **сетки**).
- **`grid_count = clamp(round(width_pct / step_pct), 10, 120)`**.
- **`order_size = round(capital / grid_count, 2)`**; **`step_pct`** в модели с округлением до 2 знаков.
- Вызов: после расчёта **`low` / `high` / `width_pct`**, если **`coin.capital is not None`** — проверка **`capital > 0`**, иначе **`RangeEngineError`**. Если **`capital is None`** — **`grid_configs`** не считаются (**`()`**).
- Дополнительно: проверка **`width_pct > 0`** перед сборкой **`RecommendedRange`**.

Публичная функция **`compute_geometric_grid_configs(width_pct, capital)`** используется движком и покрыта тестами.

### 5. JSON и `CoinRepository`

Файл: **`src/range_program/repositories/coin_repository.py`**.

- В запись монеты добавлено **`capital`** (в т.ч. **`null`**).
- В **`recommended_range`** сериализуется массив **`grid_configs`**; при отсутствии в старых файлах — пустой набор.

### 6. Валидация

Файл: **`src/range_program/validation.py`**.

- **`validate_capital(capital)`** — если не **`None`**, то должно быть **> 0** (сообщение на английском в стиле существующих **`ValidationError`**).

### 7. `CoinService`

Файл: **`src/range_program/services/coin_service.py`**.

- **`add_coin(..., capital=None)`** — с **`validate_capital`**.
- **`set_capital(symbol, capital)`** — обновление **`capital`** и **`updated_at`**.
- **`clear_capital(symbol)`** — **`capital = None`**.

### 8. CLI

Файл: **`src/range_program/cli.py`**.

| Команда | Поведение |
|--------|------------|
| **`range add SYMBOL --capital N`** | Сохраняет капитал при создании монеты (опционально). |
| **`range set-capital SYMBOL AMOUNT`** | Установить капитал. |
| **`range clear-capital SYMBOL`** | Сбросить капитал. |
| **`range recalc SYMBOL`** | Сжатый блок диапазона + при наличии капитала и ненулевых **`grid_configs`** — блок **Grid setups** (Aggressive / Balanced / Conservative). Если капитала нет — жёлтая подсказка про **`set-capital`**. |
| **`range show SYMBOL`** | Строка **`capital`**; при наличии **`grid_configs`** в **`recommended_range`** — блок **Recommended grid setups**. |
| **`range list`** | Добавлена колонка **`capital`** (или **—**). |

Используется **`DEFAULT_QUOTE_ASSET`** из **`config.py`** для подписи размера ордера.

---

## Что намеренно не входило в этап

- Минимальный размер ордера биржи, комиссии, проскальзывание.
- Изменение **`Evaluator`**, **`check`**, **`backtest`**, **`optimize`** по смыслу (они лишь могут получать **`RecommendedRange`** с дополнительным полем).
- Автовыставление ордеров.

---

## Тесты

Файл: **`tests/test_grid_config.py`** и дополнения в **`tests/test_range_engine.py`**.

Проверяются: формула и clamp, отказ при неверном **`width_pct`** / **`capital`**, roundtrip JSON с **`capital`** и **`grid_configs`**, legacy **`recommended_range`** без **`grid_configs`**, **`set_capital` / `clear_capital`**, пустые / непустые **`grid_configs`** в **`RangeEngine`** при наличии/отсутствии **`capital`**.

---

## Связь с `plan.md`

Этап добавляет **практический слой «сколько уровней и какой объём на ордер»** поверх уже существующего коридора, не подменяя расчёт диапазона. Это база для ручной настройки геометрического бота по цифрам из **`recalc`**.

---

## Итог этапа

Программа умеет хранить **капитал по монете**, при **`recalc`** дополнять **`recommended_range`** тремя **готовыми профилями сетки** (плотность и размер ордера), показывать это в **`recalc`** и **`show`**, управлять капиталом отдельными командами. Алгоритм диапазона (**`RangeEngine`** по ATR/центру) **не заменён**, а **дополнен** расчётом сетки тем же модулем.
