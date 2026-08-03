# Развёртывание Telegram signal bot на сервере

Эта инструкция рассчитана на небольшой Linux-сервер с `systemd` и доступом
через `sudo`. Бот не является постоянно работающим процессом: один запуск
проверяет рынок, отправляет новые сигналы и завершается. Таймер запускает его по
мадридскому времени с 08:01 до 22:46 на 1-й, 16-й, 31-й и 46-й минуте каждого
часа, а затем делает последний запуск в 23:01. В расписании явно указана зона
`Europe/Madrid`, поэтому переход между летним и зимним временем учитывается
автоматически независимо от системной зоны сервера.
Пропущенные запуски не догоняются после перезагрузки сервера: если сервер
включится ночью, следующий запуск будет только в разрешённом окне.

Боту не нужен входящий сетевой порт. Серверу нужен только исходящий HTTPS-доступ
к Telegram и BingX.

## 1. Подготовить секреты

Отзовите любой токен, который когда-либо попадал в исходный код или Git, и
получите новый через `@BotFather`. Не передавайте новый токен в командной строке,
чате или Git.

Для восстановления chat ID отправьте новому боту `/start`, временно задайте
`TELEGRAM_BOT_TOKEN` в окружении и запустите:

```bash
python3 -m hermes_trading.get_telegram_chat_id
```

## 2. Подготовить сервер

Установите Python 3.10+, Git и поддержку virtualenv. Для Ubuntu/Debian:

```bash
sudo apt update
sudo apt install --yes python3 python3-venv git ca-certificates tzdata
```

Создайте отдельного системного пользователя и каталоги:

```bash
sudo useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin hermes
sudo install -d -o hermes -g hermes -m 0750 /opt/hermes-trading
sudo install -d -o root -g hermes -m 0750 /etc/hermes-trading
```

Если пользователь уже существует, `useradd` завершится ошибкой; проверьте его
командой `id hermes` и продолжайте.

## 3. Загрузить и установить приложение

Перед загрузкой выполните в локальном репозитории `python3 -m pytest`. На
production-сервер устанавливаются только runtime-зависимости, без Pytest.

Клонируйте репозиторий или загрузите его другим привычным способом:

```bash
sudo -u hermes git clone <repository-url> /opt/hermes-trading/app
sudo -u hermes python3 -m venv /opt/hermes-trading/app/.venv
sudo -u hermes /opt/hermes-trading/app/.venv/bin/python -m pip install --upgrade pip
sudo -u hermes /opt/hermes-trading/app/.venv/bin/python -m pip install --editable /opt/hermes-trading/app
```

Для приватного репозитория используйте отдельный read-only deploy key. Не
копируйте личный SSH-ключ на сервер.

## 4. Настроить environment

Установите пример как закрытый конфигурационный файл:

```bash
sudo install -o root -g hermes -m 0640 \
  /opt/hermes-trading/app/.env.example \
  /etc/hermes-trading/hermes-signals-bot.env
sudoedit /etc/hermes-trading/hermes-signals-bot.env
```

Задайте новый `TELEGRAM_BOT_TOKEN` и нужный `TELEGRAM_CHAT_ID`.

Режим обработки объёма и волатильности задаётся через
`SIGNAL_METRIC_FILTER_ENABLED`:

- `0` — значение по умолчанию: бот отправляет каждый найденный паттерн, а
  метрики показывает только как информацию;
- `1` — бот отправляет сигнал только тогда, когда и объём, и волатильность как
  минимум на 10% выше обеих соответствующих свечей сравнения.

В каждом уведомлении явно указано, был фильтр включён или метрики использовались
только как информация. Время сигнала отображается как время закрытия финальной
свечи паттерна в `Europe/Madrid`.

`systemd` читает этот файл через `EnvironmentFile`; Python сам `.env` не читает.
Дополнительная библиотека для этого не нужна. Оставьте
`TELEGRAM_SSL_INSECURE=0`.

## 5. Установить service и timer

```bash
sudo install -o root -g root -m 0644 \
  /opt/hermes-trading/app/deploy/systemd/hermes-signals-bot.service \
  /etc/systemd/system/hermes-signals-bot.service
sudo install -o root -g root -m 0644 \
  /opt/hermes-trading/app/deploy/systemd/hermes-signals-bot.timer \
  /etc/systemd/system/hermes-signals-bot.timer
sudo systemctl daemon-reload
```

Сначала выполните один ручной запуск. Он может отправить реальные сообщения:

```bash
sudo systemctl start hermes-signals-bot.service
sudo systemctl status hermes-signals-bot.service
sudo journalctl -u hermes-signals-bot.service -n 100 --no-pager
```

Успешный oneshot-service после выполнения отображается как `inactive (dead)` с
результатом `status=0/SUCCESS`. Это нормально.

Включите расписание только после успешной проверки:

```bash
sudo systemctl enable --now hermes-signals-bot.timer
systemctl list-timers hermes-signals-bot.timer
```

Проверьте обе календарные строки до включения таймера:

```bash
systemd-analyze calendar '*-*-* 08..22:01,16,31,46:00 Europe/Madrid'
systemd-analyze calendar '*-*-* 23:01:00 Europe/Madrid'
```

## Проверка и эксплуатация

```bash
systemctl status hermes-signals-bot.timer
systemctl status hermes-signals-bot.service
sudo journalctl -u hermes-signals-bot.service --since today
sudo systemctl start hermes-signals-bot.service
```

Логи хранятся в journald; отдельные файлы логов не нужны. Бот не хранит runtime
state: он анализирует только свечи, закрывшиеся за последние 15 минут. Не
запускайте его вручную несколько раз в одном интервале, иначе одинаковое
уведомление может быть отправлено повторно.

## Обновление

Остановите timer, обновите код и зависимости, запустите тесты, затем верните
расписание:

```bash
sudo systemctl stop hermes-signals-bot.timer
sudo -u hermes git -C /opt/hermes-trading/app pull --ff-only
sudo -u hermes /opt/hermes-trading/app/.venv/bin/python -m pip install --editable /opt/hermes-trading/app
sudo install -o root -g root -m 0644 \
  /opt/hermes-trading/app/deploy/systemd/hermes-signals-bot.timer \
  /etc/systemd/system/hermes-signals-bot.timer
sudo systemctl daemon-reload
sudo systemctl start hermes-signals-bot.service
sudo systemctl restart hermes-signals-bot.timer
systemctl list-timers hermes-signals-bot.timer
```

Если проверка не прошла, не запускайте timer. Верните предыдущий проверенный
commit, повторите установку и ручной запуск. Environment находится вне
репозитория, поэтому обновление кода его не перезаписывает.

## Остановка и удаление

```bash
sudo systemctl disable --now hermes-signals-bot.timer
sudo systemctl stop hermes-signals-bot.service
sudo rm /etc/systemd/system/hermes-signals-bot.service
sudo rm /etc/systemd/system/hermes-signals-bot.timer
sudo systemctl daemon-reload
```

Не удаляйте `/etc/hermes-trading`, пока не сохранены секреты. Код можно удалить
отдельно после подтверждения rollback.
