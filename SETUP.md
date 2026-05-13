# Инструкция по запуску Dating Bot

## 🚀 Быстрый старт

### 1. Получи токен бота

1. Открой Telegram и найди **@BotFather**
2. Напиши `/newbot`
3. Следуй инструкциям (введи имя бота и username)
4. Скопируй полученный токен (вида `123456789:ABCdef...`)

### 2. Настрой переменные окружения

Скопируй `.env.example` в `.env` в корне проекта:

```bash
cd <корень_репо>
cp .env.example .env
```

Открой `.env` и вставь токен бота:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
```

### 3. Запусти все сервисы

```bash
docker-compose up -d
```

Это поднимет:
- ✅ PostgreSQL
- ✅ Redis
- ✅ RabbitMQ
- ✅ MinIO (S3 хранилище)
- ✅ Profile Service (порт 8001)
- ✅ Bot Service (Telegram бот)
- ✅ Prometheus + Grafana (мониторинг)

### 4. Проверь статус контейнеров

```bash
docker-compose ps
```

Все сервисы должны быть в статусе `Up`.

### 5. Протестируй бота

1. Открой Telegram
2. Найди своего бота по username
3. Напиши `/start`
4. Следуй шагам регистрации!

---

## 📋 Шаги регистрации

Бот проведёт тебя через:

1. **Имя** (мин. 2 символа)
2. **Возраст** (18-100)
3. **Пол** (Мужской/Женский/Другой)
4. **Город**
5. **О себе** (опционально, можно пропустить `/skip`)
6. **Интересы** (через запятую, можно пропустить)
7. **Фото** (1-5 штук, отправить как фото в чат)
8. **Предпочтения поиска**:
   - Кого ищешь (пол)
   - Возрастной диапазон (мин/макс)
   - Город поиска (опционально)

После завершения — появится главное меню!

---

## 🔍 Проверка API

### Profile Service API (порт 8001)

Проверить здоровье сервиса:

```bash
curl http://localhost:8001/health
```

Создать пользователя вручную:

```bash
curl -X POST http://localhost:8001/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 12345, "username": "test_user"}'
```

Получить профиль:

```bash
curl http://localhost:8001/api/v1/users/12345
```

### MinIO Console (порт 9001)

Открой в браузере: http://localhost:9001

- Логин: `minio_user`
- Пароль: `minio_pass`

Здесь можно просмотреть загруженные фото.

### Grafana (порт 3000)

Открой в браузере: http://localhost:3000

- Логин: `admin`
- Пароль: `admin`

---

## 🛠️ Полезные команды

### Посмотреть логи бота

```bash
docker logs dating-bot-service -f
```

### Посмотреть логи Profile Service

```bash
docker logs dating-profile-service -f
```

### Перезапустить сервис

```bash
docker-compose restart bot-service
```

### Остановить всё

```bash
docker-compose down
```

### Остановить и удалить данные

```bash
docker-compose down -v
```

⚠️ `-v` удалит все данные из БД!

---

## ❌ Troubleshooting

### Бот не отвечает

1. Проверь логи: `docker logs dating-bot-service`
2. Убедись что токен правильный в `.env`
3. Проверь что Profile Service работает: `curl http://localhost:8001/health`

### Profile Service не запускается

```bash
docker logs dating-profile-service
```

Частая проблема — PostgreSQL ещё не готов. Подожди 10-20 секунд.

### Ошибка при загрузке фото

Убедись что MinIO запущен:

```bash
docker logs dating-minio
```

---

## 🎯 Что работает

✅ **Bot Service** — полный FSM с пошаговой регистрацией
✅ **Profile Service** — CRUD API для пользователей, профилей, фото, предпочтений
✅ **MinIO** — хранение фотографий
✅ **PostgreSQL** — основная база данных
✅ **Redis** — хранение FSM состояний

🚧 **В разработке** (заглушки):
- Matching Service
- Ranking Service
- Notification Service
- Feed (просмотр анкет)
- Свайпы
- Уведомления о мэтчах
