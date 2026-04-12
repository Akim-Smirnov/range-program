# Этап 6: Evaluator и оценка активного диапазона

Документ фиксирует, **что реально сделано** на этом этапе в репозитории Range Program. Цель этапа: **первый практичный слой оценки** — насколько **активный диапазон** (`active_range`) согласуется с **текущей ценой** и с **рекомендуемым диапазоном** (`recommended_range`), с понятным **статусом**, **рекомендацией** и **сохранением последней проверки** в JSON — **без** `check --all`, **без** backtest, **без** уведомлений и **без** усложнённой стратегической математики.

Связанные документы: общий план — [`plan.md`](plan.md); этап 5 (движок и `recommended_range`) — [`etap-5.md`](etap-5.md); этап 4 (рынок) — [`etap-4.md`](etap-4.md).

---

## Цель этапа

1. Ввести **модель результата проверки** — **`CheckResult`** с метриками и статусом.
2. Реализовать **`Evaluator`** — только логика оценки по уже известным **`Coin`**, **цене** и диапазонам (без запросов к бирже внутри движка).
3. Реализовать **`CheckService`** — загрузка монеты, при необходимости **авто-`recalc`**, получение цены через **`MarketDataService`**, вызов **`Evaluator`**, запись **`last_check`** в хранилище.
4. Команда **`range check SYMBOL`** и расширение **`range show`** для отображения **последней проверки**.

---

## Что сделано

### 1. Модель `CheckResult`

Файл: **`src/range_program/models/check_result.py`**.

Неизменяемый dataclass с полями:

- **`symbol`**, **`current_price`**;
- **`active_low`**, **`active_high`**, **`active_center`**;
- **`recommended_low`**, **`recommended_high`**, **`recommended_center`**;
- **`distance_to_lower_pct`**, **`distance_to_upper_pct`**, **`deviation_from_active_center_pct`**;
- **`status`** (строка: один из MVP-статусов);
- **`recommendation`** (краткий текст для пользователя);
- **`checked_at`** (UTC).

Экспорт из **`src/range_program/models/__init__.py`**.

---

### 2. Сервис `Evaluator`

Файл: **`src/range_program/services/evaluator.py`**.

- Метод **`evaluate(coin, current_price) -> CheckResult`** — ожидает **`active_range`** и **`recommended_range`**; при некорректных данных выбрасывает **`EvaluatorError`** с понятным текстом (в оркестрации переводится в сообщение для CLI).
- **`active_center`** считается как **\((active\_low + active\_high) / 2\)**.
- **Метрики (MVP):**
  - **`distance_to_lower_pct`** — \((current\_price - active\_low) / active\_low \times 100\) (при `active_low = 0` в знаменателе защита даёт 0 в реализации);
  - **`distance_to_upper_pct`** — \((active\_high - current\_price) / active\_high \times 100\);
  - **`deviation_from_active_center_pct`** — \(|current\_price - active\_center| / active\_center \times 100\) (при нулевом центре — 0).

**Статусы MVP** (фиксированный **приоритет**, если несколько условий могли бы подойти):

1. **`OUT_OF_RANGE`** — цена **вне** `[active_low, active_high]`.
2. **`REPOSITION`** — цена внутри, и **относительная разница центров** \(|recommended\_center - active\_center| / active\_center > 10\%\) (при `active_center > 0`).
3. **`STALE`** — цена внутри, и **отклонение цены от `active_center`** больше **12%**.
4. **`WARNING`** — цена внутри, предыдущие пункты не сработали, и позиция в ширине диапазона **\((price - low) / (high - low)\)** попадает в **нижние 5%** или **верхние 5%** ширины (близко к границе).
5. **`OK`** — иначе.

К каждому статусу привязана **краткая рекомендация** на русском (словарь в **`evaluator.py`**).

---

### 3. Сервис `CheckService`

Файл: **`src/range_program/services/check_service.py`**.

- **`run_check(symbol) -> CheckResult`**:
  - монета должна существовать в хранилище;
  - должен быть **`active_range`**;
  - если **нет `recommended_range`**, выполняется **`RecalcService.recalc`** (автоматически, как предпочтительный вариант для MVP); при ошибке — одно понятное сообщение без длинного traceback;
  - затем **`get_current_price`**, **`Evaluator.evaluate`**, обновление монеты с **`last_check`** и **`updated_at`**.

Зависимости: **`CoinService`**, **`MarketDataService`**, **`RecalcService`**, опционально **`Evaluator`**.

Экспорт из **`src/range_program/services/__init__.py`**: **`Evaluator`**, **`EvaluatorError`**, **`CheckService`**.

---

### 4. Поле `Coin.last_check` и JSON

Файлы: **`src/range_program/models/coin.py`**, **`src/range_program/repositories/coin_repository.py`**.

- В **`Coin`** добавлено поле **`last_check: CheckResult | None`**.
- **`Coin.create`** принимает опциональный **`last_check`**.
- Репозиторий сериализует/десериализует вложенный объект **`last_check`** в **`data/coins.json`**. Записи без ключа по-прежнему читаются как **`null`**.

---

### 5. CLI

Файл: **`src/range_program/cli.py`**.

- **`range check SYMBOL`** — вызывает **`CheckService.run_check`**, выводит поля **`CheckResult`** столбцом. Ошибки домена оформляются через **`ValidationError`** / короткий текст и код выхода **1** (без «сырого» traceback при обычных сбоях).
- **`range show SYMBOL`** — после **`recommended_range`** добавлен блок **`last_check`**: **статус**, **время проверки**, **рекомендация** (если проверка уже сохранялась).

Бизнес-правила оценки **не** дублируются в CLI — только вызов сервисов и печать.

---

### 6. Тесты

Файл: **`tests/test_evaluator.py`** — сценарии статусов на синтетических монетах; для **`WARNING`** добавлен тест с подменой порога STALE (чтобы правило границы было проверяемо изолированно).

Полный прогон: **`python -m pytest tests`**.

---

## Что намеренно не входило в этап

- **`range check --all`** и массовые проверки по списку.
- Backtest, симуляции, «историческая» оценка.
- Push/Telegram и прочие уведомления.
- Расширенный набор стратегий и весов метрик сверх описанного MVP.

---

## Итог этапа

Появился **первый Evaluator**: он сопоставляет **активную сетку**, **текущую цену** и **рекомендуемый диапазон**, выдаёт **статус и рекомендацию**, сохраняет **последний результат** в **`last_check`** и выводит его через **`check`** и **`show`**. Это база для дальнейшего развития по [`plan.md`](plan.md) (массовые проверки, журналы, уточнение правил — отдельными этапами).
