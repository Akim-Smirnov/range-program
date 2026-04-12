# Этап 5: первый Range Engine и рекомендуемый диапазон

Документ фиксирует, **что реально сделано** на этом этапе в репозитории Range Program. Цель этапа: **впервые рассчитывать и сохранять рекомендуемый диапазон** для монеты по простому MVP-алгоритму (центр + ATR + ограничения по ширине), **без** статусов `OK/WARNING`, **без** evaluator, **без** `check --all`, **без** backtest и **без** набора альтернативных стратегий.

Связанные документы: общий план — [`plan.md`](plan.md); этап 4 (рынок) — [`etap-4.md`](etap-4.md); этап 3 (модель и JSON) — [`etap-3.md`](etap-3.md).

---

## Цель этапа

1. Ввести **модель результата расчёта** — рекомендуемый диапазон с метаданными.
2. Реализовать **`RangeEngine`** — чистый расчёт по данным монеты, **текущей цене** и **списку свечей**.
3. Оркестрация **`RecalcService`**: лимит свечей, вызов **`MarketDataService`**, вызов движка, **сохранение** в **`data/coins.json`**.
4. Команда **`range recalc SYMBOL`** и расширение **`range show`** для отображения сохранённого **`recommended_range`**.

---

## Что сделано

### 1. Модель `RecommendedRange`

Файл: **`src/range_program/models/recommended_range.py`**.

Поля (неизменяемый dataclass):

- **`low`**, **`high`**, **`center`** (float);
- **`width_pct`** — полная ширина диапазона в процентах от центра: \((high - low) / center \times 100\);
- **`calculated_at`** (UTC);
- **`center_method`**, **`width_method`** (строки, как использовались при расчёте).

Экспорт из **`src/range_program/models/__init__.py`**.

---

### 2. Расширение `Coin` и JSON

Файлы: **`src/range_program/models/coin.py`**, **`src/range_program/repositories/coin_repository.py`**.

- В **`Coin`** добавлено поле **`recommended_range`** (`RecommendedRange | None`, по умолчанию `null`).
- **`Coin.create(...)`** принимает опциональный **`recommended_range`**.
- Репозиторий сериализует/десериализует вложенный объект **`recommended_range`** в **`data/coins.json`** (рядом с **`active_range`**). Записи без этого ключа по-прежнему читаются (значение `null`).

---

### 3. `RangeEngine` (MVP-алгоритм)

Файл: **`src/range_program/services/range_engine.py`**.

Класс **`RangeEngine`**, исключение **`RangeEngineError`** — короткие сообщения для CLI.

Метод:

- **`calculate_range(coin, *, current_price, candles) -> RecommendedRange`**

Поддержка по полям монеты:

- **`center_method`:**  
  - **`price`** — центр = **текущая цена** (`current_price` с рынка);  
  - **`ema`** — центр = **EMA(20)** по **close** последовательности свечей (после сортировки по времени).
- **`width_method`:** только **`atr`** (другие значения → ошибка).

Ширина (до ограничений):

- **ATR(14)** по классической схеме Уайлдера на **true range**;
- половина ширины диапазона в цене = **`ATR × multiplier`**, множитель по **`mode`**:  
  **conservative = 6**, **balanced = 4**, **aggressive = 3**.

Границы:

- симметрично: **`low = center - half_width`**, **`high = center + half_width`**.

Ограничения **после** шага ATR (полная ширина в %% от центра):

| mode         | мин. полная ширина | макс. полная ширина |
|-------------|---------------------|----------------------|
| conservative | 16%                | 40%                  |
| balanced     | 12%                | 30%                  |
| aggressive   | 8%                 | 20%                  |

Если итоговая ширина уже внутри коридора — половина ширины не меняется; если уже — симметрично сжимается или расширяется до ближайшей границы по процентам.

**`width_pct`** в результате — **финальная** полная ширина после clamp.

Минимальное число свечей контролируется (в т.ч. для EMA(20) и стартового блока ATR); при нехватке данных выбрасывается **`RangeEngineError`**.

---

### 4. `RecalcService`

Файл: **`src/range_program/services/recalc_service.py`**.

- **`estimate_candle_limit(timeframe, lookback_days)`** — грубый перевод дней в число свечей (парсинг строк вида `4h`, `1d` и т.п.), с полом **не ниже 80** и **не выше 1000** (ограничение запроса к бирже).
- **`RecalcOutcome`** — удобная сводка для CLI: символ, режим, текущая цена, **`RecommendedRange`**.
- **`RecalcService.recalc(symbol)`:**  
  монета из **`CoinService`** → свечи **`get_ohlcv(symbol, coin.timeframe, limit)`** → цена **`get_current_price`** → **`RangeEngine.calculate_range`** → **`dataclasses.replace`** с **`recommended_range`** и **`updated_at`** → **`update_coin`**.

Зависимости: **`CoinService`**, **`MarketDataService`**, **`RangeEngine`** (по умолчанию создаётся внутри).

Экспорт из **`src/range_program/services/__init__.py`**: в том числе **`RangeEngine`**, **`RangeEngineError`**, **`RecalcService`**, **`RecalcOutcome`**.

---

### 5. CLI

Файл: **`src/range_program/cli.py`**.

- **`range recalc SYMBOL`** — запуск **`RecalcService.recalc`**; вывод: символ, текущая цена, center/low/high, **`width_pct`**, **`center_method`**, **`width_method`**, **`mode`**, **`calculated_at`**. Ошибки домена (**нет монеты**, **рынок**, **движок**) — краткий текст, код выхода **1**, без длинного traceback.
- **`range show SYMBOL`** — после **`active_range`** добавлен блок **`recommended_range`** (или явное «нет»), затем по-прежнему попытка показать **last_price** с биржи (этап 4).

Логика расчёта **не** встроена в обработчики Typer: только вызовы сервисов.

---

### 6. Тесты

Файл: **`tests/test_range_engine.py`** — сценарии на синтетических свечах (EMA/price, неподдерживаемый **`width_method`**).

Полный прогон: **`python -m pytest tests`**.

---

## Что намеренно не входило в этап

- Статусы актуальности диапазона, **evaluator**, сравнение с **`active_range`** в виде готовых вердиктов.
- **`range check`**, **`range check --all`**, сетевые «проверки портфеля».
- Backtest и сравнение нескольких стратегий.
- Расширенный зоопарк **`center_method`** / **`width_method`** сверх описанного MVP.

---

## Итог этапа

Появился **первый сквозной сценарий**: рыночные данные → **RangeEngine** → **`RecommendedRange`** в **`coins.json`** → вывод в **`recalc`** и **`show`**. Это база для следующих этапов по [`plan.md`](plan.md) (оценка относительно активного диапазона, статусы, проверки по списку монет и т.д.).
