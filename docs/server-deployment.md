# Развёртывание Telegram signal bot на сервере

Эта инструкция рассчитана на небольшой Linux-сервер с `systemd` и доступом
через `sudo`. Бот не является постоянно работающим процессом: один запуск
проверяет рынок, отправляет новые сигналы и завершается. Таймер запускает его на
1-й, 16-й, 31-й и 46-й минуте каждого часа, повторяя прежнее локальное
расписание macOS.

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
sudo apt install --yes python3 python3-venv git ca-certificates
```

Создайте отдельного системного пользователя и каталоги:

```bash
sudo useradd --system --home /var/lib/hermes-trading --shell /usr/sbin/nologin hermes
sudo install -d -o hermes -g hermes -m 0750 /opt/hermes-trading
sudo install -d -o hermes -g hermes -m 0750 /var/lib/hermes-trading
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

Задайте новый `TELEGRAM_BOT_TOKEN`, нужный `TELEGRAM_CHAT_ID` и измените путь:

```dotenv
HERMES_SENT_SIGNALS_PATH=/var/lib/hermes-trading/signals_bot_sent.json
```

`systemd` читает этот файл через `EnvironmentFile`; дополнительная Python-библиотека
для `.env` не нужна. Оставьте `TELEGRAM_SSL_INSECURE=0`.

## 5. Перенести историю отправленных сигналов

Файл `signals_bot_sent.json` не даёт боту повторно отправлять уже известные
сигналы. Перед первым серверным запуском скопируйте текущий локальный файл, если
он существует:

```bash
scp src/signals_bot_sent.json <server>:/tmp/signals_bot_sent.json
ssh <server> sudo install -o hermes -g hermes -m 0600 \
  /tmp/signals_bot_sent.json /var/lib/hermes-trading/signals_bot_sent.json
```

После проверки удалите временную копию из `/tmp`. Если начать с пустого state,
первый запуск может повторно отправить старые сигналы.

## 6. Установить service и timer

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

## Проверка и эксплуатация

```bash
systemctl status hermes-signals-bot.timer
systemctl status hermes-signals-bot.service
sudo journalctl -u hermes-signals-bot.service --since today
sudo systemctl start hermes-signals-bot.service
```

Логи хранятся в journald; отдельные файлы логов не нужны. Проверяйте, что
`/var/lib/hermes-trading/signals_bot_sent.json` обновляется после запусков.

## Обновление

Остановите timer, обновите код и зависимости, запустите тесты, затем верните
расписание:

```bash
sudo systemctl stop hermes-signals-bot.timer
sudo -u hermes git -C /opt/hermes-trading/app pull --ff-only
sudo -u hermes /opt/hermes-trading/app/.venv/bin/python -m pip install --editable /opt/hermes-trading/app
sudo systemctl start hermes-signals-bot.service
sudo systemctl start hermes-signals-bot.timer
```

Если проверка не прошла, не запускайте timer. Верните предыдущий проверенный
commit, повторите установку и ручной запуск. Environment и state находятся вне
репозитория, поэтому обновление кода их не перезаписывает.

## Остановка и удаление

```bash
sudo systemctl disable --now hermes-signals-bot.timer
sudo systemctl stop hermes-signals-bot.service
sudo rm /etc/systemd/system/hermes-signals-bot.service
sudo rm /etc/systemd/system/hermes-signals-bot.timer
sudo systemctl daemon-reload
```

Не удаляйте `/etc/hermes-trading` и `/var/lib/hermes-trading`, пока не сохранены
секреты и state. Код можно удалить отдельно после подтверждения rollback.
