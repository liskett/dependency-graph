# Dependency Graph Visualizer

CLI-приложение для анализа зависимостей пакетов Rust (Cargo).
Практическая работа № 2, вариант 19.

## Этапы работы

1. Настройка CLI: параметры командной строки и обработка ошибок.
2. Сбор прямых зависимостей заданной версии Cargo-пакета.
3. Рекурсивный BFS, транзитивные зависимости, глубина, циклы, версионированный тестовый репозиторий.

Этапы 4 и 5 пока не реализованы. Выходной SVG-файл на этапе 3 не создаётся.

## Параметры

| Параметр | Назначение |
| --- | --- |
| `--package` | Имя корневого пакета, обязательно. |
| `--repository` | URL Cargo-реестра или путь к JSON, обязательно. |
| `--test-mode` | Читать тестовый репозиторий вместо Cargo-реестра. |
| `--version` | Точная версия корневого пакета, обязательно. |
| `--output` | Имя будущего SVG-файла; по умолчанию `dependency_graph.svg`. |
| `--max-depth` | Максимальная глубина по рёбрам, по умолчанию `5`. |

Ошибки ввода обрабатываются в CLI. Для глубины `0` выводится только корневой узел, для глубины `1` — его прямые зависимости.

## Модули и функции

- `src/config.py`: `build_parser`, `parse_config` читают аргументы; `validate_package`, `validate_version`, `validate_output`, `validate_depth`, `is_http_url` проверяют значения; `AppConfig.as_dict` возвращает конфигурацию как словарь.
- `src/cargo.py`: `build_dependencies_url`, `build_versions_url` формируют API-адреса; `fetch_json` получает JSON; `parse_dependencies` декодирует зависимости; `fetch_dependencies` получает прямые зависимости; `resolve_dependency_version` подбирает точную версию через `version_satisfies`; `load_test_dependencies` читает старый тестовый формат, `get_direct_dependencies` выбирает источник. Вспомогательные функции проверяют записи и ограничения версий.
- `src/versioned_repository.py`: `VersionedRepository` читает тестовый JSON, проверяет имена, версии и ссылки; метод `dependencies` возвращает зависимости конкретной версии. Внутренние методы `_read_graph`, `_parse_graph`, `_parse_dependency`, `_check_package`, `_check_version`, `_validate_references` отвечают за валидацию.
- `src/graph.py`: `node_id` создаёт идентификатор узла; `GraphBuilder.build` запускает обход; `_expand_level` рекурсивно обрабатывает уровни BFS; `_add_edges` записывает рёбра; `build_dependency_graph` — публичная функция построения графа.
- `src/main.py`: `make_loaders` выбирает источник данных, `test_version` берёт точную тестовую версию, `print_graph` выводит граф, `main` управляет запуском приложения. Внутренние загрузчики реестра получают зависимости и разрешают версии.

## Третий этап

Каждый узел обозначается как `ИМЯ@ВЕРСИЯ`, например `A@1.0.0`.

Таким образом, `B@1.0.0` и `B@2.0.0` — разные узлы, у которых могут быть разные зависимости.

Граф обходится по уровням (BFS). Обработка следующего уровня выполняется рекурсивным вызовом. Уже обнаруженные версии пакетов повторно не раскрываются, что останавливает циклы. Рёбра цикла при этом сохраняются в графе.

Для реального Cargo-реестра данные читаются через HTTP API без использования Cargo и сторонних библиотек. Для транзитивной зависимости выбирается последняя стабильная неотозванная версия, совместимая с поддерживаемыми требованиями Cargo.

Этот упрощённый алгоритм не заменяет полноценное разрешение зависимостей Cargo.

## Тестовый JSON с версиями

В `tests/data/versioned_graph.json` ключ верхнего уровня — имя пакета (только заглавные латинские буквы). Далее указаны точные версии пакета и списки его прямых зависимостей:

```json
{
  "A": {
    "1.0.0": [{"name": "B", "version": "1.0.0"}],
    "2.0.0": [{"name": "B", "version": "2.0.0"}]
  },
  "B": {
    "1.0.0": [],
    "2.0.0": []
  }
}
```

Тестовый репозиторий проверяется на корректность имён, версий, структуры JSON и ссылок на существующие версии пакетов.

Исходный `tests/data/test_graph.json` сохранён как тестовые данные второго этапа для проверки получения прямых зависимостей.

## Запуск

Нужен Python 3.10 или новее. Дополнительные Python-библиотеки не требуются.

В Linux/macOS используйте `./run.sh`.

### Полный граф с циклом

```bash
./run.sh --package A --version 1.0.0 \
  --repository tests/data/versioned_graph.json \
  --test-mode --max-depth 5
```

### Сравнение версий одной и той же библиотеки

```bash
./run.sh --package A --version 2.0.0 \
  --repository tests/data/versioned_graph.json \
  --test-mode --max-depth 5
```

### Проверка ограничения глубины

```bash
./run.sh --package A --version 1.0.0 \
  --repository tests/data/versioned_graph.json \
  --test-mode --max-depth 1
```

### Пакет без зависимостей

```bash
./run.sh --package D --version 1.0.0 \
  --repository tests/data/versioned_graph.json \
  --test-mode --max-depth 5
```

### Реальный Cargo-реестр

Для работы необходим интернет:

```bash
./run.sh --package serde --version 1.0.0 \
  --repository https://crates.io --max-depth 2
```

## Проверка и тесты

Проект написан на Python и не требует отдельной сборки.

Проверить синтаксис и запустить тесты можно так:

```bash
python3 -m compileall -q src tests
python3 -m unittest discover -s tests -v
```

Тесты третьего этапа проверяют порядок BFS, циклы, общие зависимости, независимые версии одного пакета, максимальную глубину и ошибки входного тестового файла.

## Структура проекта

```text
dependency-graph/
├── README.md
├── .gitignore
├── run.sh
├── src/
│   ├── __init__.py
│   ├── cargo.py
│   ├── config.py
│   ├── graph.py
│   ├── main.py
│   └── versioned_repository.py
└── tests/
    ├── data/
    │   ├── test_graph.json
    │   └── versioned_graph.json
    ├── test_cargo.py
    ├── test_config.py
    └── test_graph.py
```