# Labyrinth

Графическая игра-лабиринт на Python и `Arcade`.

## Возможности

- случайная генерация лабиринта;
- режим автопрохождения;
- ручной режим с `WASD` и стрелками;
- туман войны и память исследованных клеток;
- плавное движение, камера и атмосферный HUD;
- консольный fallback-режим.

## Запуск графической версии

```bash
.venv/bin/python main.py
```

## Запуск консольной версии

```bash
.venv/bin/python main.py --console
```

## Установка зависимостей

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Тесты

```bash
.venv/bin/python -m unittest test_maze.py
```
