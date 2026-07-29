# Размещение в FastPanel

Параметры сайта:

- домен: `maxbot.complect.org`;
- пользователь: `maxbot_compl_usr`;
- папка: `/var/www/maxbot_compl_usr/data/www/maxbot.complect.org`;
- внутренний адрес: `127.0.0.1:8765`.

## 1. Загрузка

Загрузить содержимое проекта в папку сайта через файловый менеджер FastPanel.
В корне должны находиться `pyproject.toml`, `requirements.txt`, папки `src` и
`deploy`.

## 2. Окружение Python

Выполнить от `root`:

```bash
cd /var/www/maxbot_compl_usr/data/www/maxbot.complect.org
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install .
chown -R maxbot_compl_usr:maxbot_compl_usr /var/www/maxbot_compl_usr/data/www/maxbot.complect.org
```

## 3. Секретные настройки

Создать файл `/var/www/maxbot_compl_usr/data/.env`. Не размещать его в папке
сайта и не присылать его содержимое в чат.

До регистрации события нужны:

```text
BITRIX_WEBHOOK_BASE_URL=секретный_адрес_входящего_вебхука
BITRIX_EVENT_TOKEN=защитный_токен_исходящего_события
BITRIX_EVENT_DOMAIN=crm.complect.org
BITRIX_PORTAL_URL=https://crm.complect.org
BITRIX_ALLOWED_DEAL_IDS=43528
JOURNAL_PATH=/var/www/maxbot_compl_usr/data/test_journal.sqlite3
```

На первом запуске `BITRIX_EVENT_TOKEN` можно оставить пустым: маршрут проверки
работы доступен без него, а приём событий останется отключён.

Ограничить доступ:

```bash
chown maxbot_compl_usr:maxbot_compl_usr /var/www/maxbot_compl_usr/data/.env
chmod 600 /var/www/maxbot_compl_usr/data/.env
```

## 4. Служба

```bash
cp /var/www/maxbot_compl_usr/data/www/maxbot.complect.org/deploy/maxbot.service /etc/systemd/system/maxbot.service
systemctl daemon-reload
systemctl enable --now maxbot.service
systemctl status maxbot.service --no-pager
```

## 5. Проверка

Открыть:

```text
https://maxbot.complect.org/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

Если сайт показывает ошибку, безопасно посмотреть последние строки:

```bash
journalctl -u maxbot.service -n 50 --no-pager
```

Перед публикацией вывода убедиться, что в нём нет токенов или персональных
данных.

## Тестовый опрос

Служба `maxbot-poller.service` выполняет чтение раз в 10 секунд. Пока в
`BITRIX_ALLOWED_DEAL_IDS` указано `43528`, API-запрос ограничен только этой
тестовой сделкой. Служба не отправляет сообщения и не записывает персональные
данные.

Не включать её до добавления `BITRIX_WEBHOOK_BASE_URL` в секретный `.env`.
