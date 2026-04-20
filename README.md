# Range Program

Консольное приложение для расчёта, хранения и контроля **рабочих диапазонов** сеточных ботов по нескольким монетам: рекомендуемый диапазон по рынку, активный диапазон (ваша сетка), проверки, история, упрощённый backtest и сравнение режимов. К бирже обращается только за **котировками и свечами** (чтение), без торговли.

## Возможности

- **Командный режим** — привычный CLI на [Typer](https://github.com/tiangolo/typer): `range add`, `range recalc`, `range check`, `range backtest` и др.
- **Интерактивное меню** — `range menu` или `range ui`: разделы (Coins, Market, Range, Checks, History, Backtest, Optimize), выбор монет из списка, пошаговые вопросы; в Range analysis есть **recalc с параметрами** (анализ/override без сохранения, с опциональным сохранением) ([этап 13](docs/etap-13.md)).
- Несколько бирж и котировок через [ccxt](https://github.com/ccxt/ccxt), fallback и кэш пары в монете ([этап 12](docs/etap-12.md)).
- Локальные данные в `data/` (`coins.json`, `check_history.json`, логи).

## Требования

- Python **3.10+**
- Интернет для команд, которые запрашивают рынок

## Установка

Из корня репозитория (где `pyproject.toml`):

```bash
pip install -e .
```

Зависимости: **Typer**, **ccxt**, **questionary** (меню) — см. `pyproject.toml`.

## Быстрый старт

**Справка по всем подкомандам:**

```bash
range --help
```

**Пример в командной строке:**

```bash
range add BTC
range recalc BTC
range list
```

**Интерактивный режим:**

```bash
range menu
```

Подробная инструкция пользователя, таблица команд и сценарии — **[`docs/instrukciya.md`](docs/instrukciya.md)**.

## Документация в `docs/`

| Файл | Описание |
|------|----------|
| [`instrukciya.md`](docs/instrukciya.md) | Полная инструкция: CLI и меню, команды, данные, типичные сценарии |
| [`plan.md`](docs/plan.md) | Идеи и план проекта (часть пунктов — на будущее) |
| [`etap-2.md`](docs/etap-2.md) … [`etap-13.md`](docs/etap-13.md) | Что реализовано по этапам разработки |

## Структура репозитория (кратко)

```text
src/range_program/   # пакет: CLI, меню, сервисы, модели, репозитории
tests/               # pytest
docs/                # инструкция и этапы
data/                # локальные JSON и логи (см. .gitignore)
```

## Версия

Номер версии указан в [`pyproject.toml`](pyproject.toml) (`[project].version`).
