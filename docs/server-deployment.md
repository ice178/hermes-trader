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

- `1` — значение по умолчанию: бот отправляет сигнал только тогда, когда и
  объём, и волатильность как минимум на 10% выше обеих соответствующих свечей
  сравнения.
- `0` — явное отключение фильтра: бот отправляет каждый найденный паттерн, а
  метрики показывает только как информацию.

Волатильность здесь — диапазон свечи `high - low`. Обе метрики должны пройти
порог относительно каждой из двух опорных свечей. Отсутствующее или пустое
значение включает фильтр. Старое значение `0` в рабочем environment продолжает
отключать его, даже после обновления кода.

В уведомлении сравнение объёма или волатильности показывается только тогда,
когда соответствующая метрика минимум на 10% выше обеих свечей сравнения.
Время сигнала отображается как время закрытия финальной свечи паттерна в
`Europe/Madrid`.

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

Логи хранятся в journald; отдельные файлы логов не нужны. Сканер не хранит
состояние отправленных сигналов: он анализирует только свечи, закрывшиеся за последние 15 минут. Не
запускайте его вручную несколько раз в одном интервале, иначе одинаковое
уведомление может быть отправлено повторно.

Для ручных уровней и зон доступен отдельный постоянно работающий Telegram-демон.
Он хранит области и состояние команд в SQLite вне Git-каталога. Установка,
команды и backup описаны в [руководстве ручных уровней](manual-levels.md).

## Обновление

### Подготовить релиз локально

Сервер обновляется из `origin/main`: локальные изменения и незамерженный PR
туда не попадут. Для текущего релиза включите изменения задач 007–010, в том
числе новые untracked-файлы сервиса уровней и исторического сканера.

1. Выполните `git status --short`, просмотрите diff и новые файлы. Не добавляйте
   `.env`, базы SQLite, логи и результаты сканирования.
2. Запустите `python3 -m pytest`, `bash -n deploy/update-server.sh` и
   `git diff --check`.
3. Создайте ветку, добавьте файлы релиза и проверьте `git diff --cached`.
   Сделайте commit, push, затем PR и merge в `main`.
4. Запишите SHA итогового commit в `main`: с ним сравнивается версия на сервере.
   Создание GitHub Release или тега само по себе не запускает деплой.

### Включить фильтр на существующем сервере

Фильтр доступен и в предыдущей версии: для уменьшения числа уведомлений можно
сначала поменять настройку, не дожидаясь релиза.

```bash
sudoedit /etc/hermes-trading/hermes-signals-bot.env
```

Замените существующую строку (не добавляйте второй экземпляр) на:

```dotenv
SIGNAL_METRIC_FILTER_ENABLED=1
```

Не заменяйте рабочий environment файлом `.env.example`. Скрипт обновления
сохраняет его, поэтому старое значение `0` нужно изменить вручную. Настройка
будет прочитана при следующем запуске scanner; перезапуск timer и
`daemon-reload` только для изменения environment не требуются. Уже работающий
scan завершится со старой настройкой.

### Обновить код и проверить результат

После первого появления скрипта на сервере один раз получите его обычным
fast-forward обновлением:

```bash
sudo systemctl stop hermes-signals-bot.timer
sudo systemctl stop hermes-signals-bot.service
sudo systemctl stop hermes-levels-bot.service # только если listener уже установлен
sudo -u hermes git -C /opt/hermes-trading/app switch main
sudo -u hermes git -C /opt/hermes-trading/app pull --ff-only
sudo /opt/hermes-trading/app/deploy/update-server.sh
```

Остановка перед первым `pull` нужна только для безопасного bootstrap, пока
скрипта ещё нет на сервере. Все последующие обновления запускаются одной
командой (если listener уже работает, используйте версию updater с поддержкой
`hermes-levels-bot.service`; при старом updater сначала выполните bootstrap выше):

```bash
sudo /opt/hermes-trading/app/deploy/update-server.sh
```

Скрипт проверяет чистоту tracked-файлов, заранее получает и валидирует
`origin/main`, останавливает timer и текущий scan, выполняет только
fast-forward обновление, обновляет virtualenv, устанавливает оба systemd unit,
проверяет их и включает timer. Environment находится вне репозитория и не
перезаписывается. Скрипт не запускает live scan вручную; после включения timer
уведомления возобновятся по расписанию.

Если `hermes-levels-bot.service` уже включён или работает, скрипт также
останавливает его перед обновлением кода и запускает после проверки units.
При первой установке новый демон автоматически не включается. База уровней
остаётся вне checkout и сохраняется при обновлении. После перезапуска listener
может отправить накопленные ответы на команды; сканирование рынка не запускается.

Проверьте SHA, состояние timer и результат ближайшего планового scan:

```bash
sudo -u hermes git -C /opt/hermes-trading/app rev-parse HEAD
systemctl is-active hermes-signals-bot.timer
systemctl list-timers --no-pager hermes-signals-bot.timer
systemctl show hermes-signals-bot.service -p Result -p ExecMainStatus
sudo journalctl -u hermes-signals-bot.service --since today --no-pager
```

SHA должен совпасть с подготовленным релизом в `main`. До первого нового scan
`Result` может относиться к старому запуску; смотрите время в журнале.
Завершившийся oneshot с `Result=success` и `ExecMainStatus=0` может быть
`inactive` — это нормально. После включения фильтра отсутствие сигналов само
по себе не означает ошибку: подходящих паттернов может не быть.

Для первого включения команд уровней отдельно настройте `LEVELS_DB_PATH` и
`TELEGRAM_ALLOWED_USER_IDS`, затем выполните шаги
[первой установки listener](manual-levels.md#первая-установка-на-сервере).
Для обычных отфильтрованных сигналов listener не требуется.

Если ошибка произошла после остановки production, timer намеренно остаётся
остановленным. Исправьте указанную ошибку или верните напечатанный предыдущий
commit, затем снова запустите скрипт. Не включайте timer поверх частично
установленного обновления.

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
