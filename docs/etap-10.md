# Этап 10: сравнение режимов диапазона и простой score

Документ фиксирует, **что реально сделано** на этом этапе в репозитории Range Program. Цель этапа: на **одной и той же истории** для монеты сравнить три режима **`RangeEngine`** (**`conservative`**, **`balanced`**, **`aggressive`**) через уже существующий **`run_backtest`**, свести метрики в **`ModeResult`**, посчитать **простой числовой score** и вывести таблицу + «лучший» режим — **без** ML, **без** перебора сотен параметров, **без** оптимизации периода ATR и **без** автоматического изменения настроек монеты.

Связанные документы: [`plan.md`](plan.md); этап 9 (backtest) — [`etap-9.md`](etap-9.md); этап 11 (капитал и сетка) — [`etap-11.md`](etap-11.md).

---

## Цель этапа

1. Сервис **`compare_modes(coin, days, …) -> list[ModeResult]`** — три прогона backtest с **`replace(coin, mode=…)`** для фиксированного порядка режимов.
2. Функция **`compute_mode_score(...)`** — линейная эвристика по **`lifetime_days`**, **`ok_days`**, **`stale_days`**, **`max_deviation_pct`**.
3. Вспомогательная **`best_mode_result(results)`** — режим с максимальным **`score`** (при равенстве — детерминированный выбор через **`max`**).
4. CLI: **`range optimize SYMBOL --days N`** и **`range suggest SYMBOL`** (с опциональным **`--days`**).

---

## Что сделано

### 1. Модель `ModeResult`

Файл: **`src/range_program/models/mode_result.py`**.

Поля: **`mode`**, **`lifetime_days`**, **`hit_upper`**, **`hit_lower`**, **`max_deviation_pct`**, **`stale_days`**, **`ok_days`**, **`warning_days`**, **`score`**, **`summary`**.

- **`ok_days` / `warning_days` / `stale_days`** — перевод счётчиков шагов из **`BacktestResult`** в «дни» делением на **`bars_per_day(coin.timeframe)`** (та же идея, что и в выводе **`range backtest`**).
- **`WARNING`** участвует в таблице, но **не** входит в формулу **`score`** (только **`OK`** и **`STALE`** наряду с **`lifetime_days`** и **`max_deviation_pct`**).

Экспорт: **`range_program.models.ModeResult`**.

---

### 2. Сервис `optimizer`

Файл: **`src/range_program/services/optimizer.py`**.

- Константа **`MODES_COMPARISON_ORDER`**: **`conservative` → `balanced` → `aggressive`** — порядок строк в таблице и порядок вызовов **`run_backtest`**.
- Для каждого режима вызывается **`run_backtest(coin_with_mode, days, market=…, engine=…, evaluator=…)`** — логика движка и оценщика **не дублируется**; **`RangeEngine`** не менялся.
- **`summary`** (строка на английском): режим, **`score`**, приблизительный **`lifetime`**, кто первым вышел за границу (**lower** / **upper** / не было выхода в окне).

Ошибки те же, что у backtest (**`ValidationError`** при недостатке свечей, слишком длинном окне и т.д.).

---

### 3. Формула score

Реализована в **`compute_mode_score`**:

```text
score = lifetime_days
        + ok_days * 0.5
        - stale_days * 0.7
        - (max_deviation_pct * 0.2)
```

Смысл: дольше «жизнь» диапазона и больше шагов в **OK** — лучше; много **STALE** и большое отклонение от центра — хуже. Короткий выход за границы отражается через меньший **`lifetime_days`**.

---

### 4. CLI

Файл: **`src/range_program/cli.py`**.

- **`_print_mode_comparison_table`** — колонки: **MODE**, **LIFETIME**, **OK**, **WARNING**, **STALE**, **DEV%**, **SCORE** (числа с одним знаком после запятой, кроме процентов отклонения).

| Команда | Поведение |
|--------|------------|
| **`range optimize SYMBOL --days N`** | Обязательный **`--days`** / **`-d`**. Таблица + строка **`Best mode: …`**. |
| **`range suggest SYMBOL`** | То же сравнение; **`--days`** по умолчанию **`DEFAULT_LOOKBACK_DAYS`** (60). Дополнительно: текст, что **`mode` нужно сменить вручную** (например **`data/coins.json`** или **`range remove` + `range add --mode …`**), напоминание про **`range recalc`**, вывод **текущего** **`mode`** из хранилища. **Автосохранения нет.** |

Логирование: **`log.info("optimize …")`**, **`log.info("suggest …")`**.

---

### 5. Тесты

Файл: **`tests/test_optimizer.py`**.

- Проверка **`compute_mode_score`** на соответствие формуле.
- **`compare_modes`** на синтетических свечах: три строки, порядок режимов, непустой **`summary`**, **`best_mode_result`**.
- Проброс **`ValidationError`**, если окно требует больше **1000** свечей (как в **`run_backtest`**).

---

## Что намеренно не входило в этап

- Обучение моделей, случайный поиск параметров, оптимизация **`EMA_PERIOD`** / **`ATR_PERIOD`**.
- Автоматическое обновление **`coins.json`** или новая команда **`set-mode`** (только подсказки в **`suggest`**).
- Визуализации и экспорт отчётов.

---

## Пример

```bash
range optimize BTC --days 60
range suggest BTC
range suggest BTC --days 30
```

---

## Связь с `plan.md`

Этап даёт **первый осмысленный способ** сравнить режимы на истории одной монеты и выбрать настройки вручную; он опирается на этап 9 и не заменяет **`check`**, **`recalc`** и хранение монеты.

---

## Итог этапа

Программа **сравнивает три режима** на общем периоде, показывает таблицу метрик и **лучший режим по score**; команда **`suggest`** помогает перенести вывод в практику **без автоматического применения**. Это задел под более «адаптивные» сценарии из плана, без усложнения ядра **`RangeEngine`**.
