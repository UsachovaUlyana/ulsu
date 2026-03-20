# Схема базы данных Dating Bot

## ER-диаграмма

```mermaid
erDiagram
    users {
        int id PK
        bigint telegram_id UK "NOT NULL"
        varchar username "NULLABLE"
        varchar referral_code UK "NOT NULL"
        int referred_by FK "NULLABLE → users"
        boolean is_active "DEFAULT TRUE"
        timestamp created_at "DEFAULT NOW()"
        timestamp updated_at "DEFAULT NOW()"
        timestamp last_active "DEFAULT NOW()"
    }

    profiles {
        int id PK
        int user_id FK, UK "NOT NULL → users"
        varchar name "NOT NULL"
        smallint age "NOT NULL, CHECK 18..100"
        varchar gender "NOT NULL (male/female/other)"
        varchar city "NOT NULL"
        text bio "NULLABLE"
        text_arr interests "NULLABLE"
        boolean is_complete "DEFAULT FALSE"
        timestamp created_at "DEFAULT NOW()"
        timestamp updated_at "DEFAULT NOW()"
    }

    photos {
        int id PK
        int profile_id FK "NOT NULL → profiles"
        varchar s3_key "NOT NULL"
        varchar s3_bucket "DEFAULT photos"
        boolean is_primary "DEFAULT FALSE"
        smallint upload_order "NOT NULL"
        timestamp created_at "DEFAULT NOW()"
    }

    preferences {
        int id PK
        int user_id FK, UK "NOT NULL → users"
        varchar target_gender "NOT NULL (male/female/any)"
        smallint age_min "DEFAULT 18"
        smallint age_max "DEFAULT 100"
        varchar city "NULLABLE"
        int max_distance "NULLABLE (км)"
        timestamp created_at "DEFAULT NOW()"
        timestamp updated_at "DEFAULT NOW()"
    }

    swipes {
        int id PK
        int swiper_id FK "NOT NULL → users"
        int swiped_id FK "NOT NULL → users"
        varchar action "NOT NULL (like/skip)"
        timestamp created_at "DEFAULT NOW()"
    }

    matches {
        int id PK
        int user1_id FK "NOT NULL → users (меньший ID)"
        int user2_id FK "NOT NULL → users (больший ID)"
        boolean is_active "DEFAULT TRUE"
        boolean chat_initiated "DEFAULT FALSE"
        timestamp created_at "DEFAULT NOW()"
        timestamp updated_at "DEFAULT NOW()"
    }

    ratings {
        int id PK
        int user_id FK, UK "NOT NULL → users"
        float primary_score "DEFAULT 0.0 (0-100)"
        float profile_completeness "DEFAULT 0.0 (0-1)"
        float photo_count_score "DEFAULT 0.0 (0-1)"
        float behavioral_score "DEFAULT 0.0 (0-100)"
        int likes_received "DEFAULT 0"
        float like_ratio "DEFAULT 0.0 (0-1)"
        float match_ratio "DEFAULT 0.0 (0-1)"
        float chat_initiation_rate "DEFAULT 0.0 (0-1)"
        float activity_score "DEFAULT 0.0 (0-1)"
        float combined_score "DEFAULT 0.0"
        float referral_bonus "DEFAULT 0.0"
        timestamp last_calculated_at "NULLABLE"
        timestamp created_at "DEFAULT NOW()"
        timestamp updated_at "DEFAULT NOW()"
    }

    referrals {
        int id PK
        int referrer_id FK "NOT NULL → users"
        int referred_id FK, UK "NOT NULL → users"
        boolean bonus_applied "DEFAULT FALSE"
        timestamp created_at "DEFAULT NOW()"
    }

    users ||--|| profiles : "1:1 — имеет анкету"
    users ||--|| preferences : "1:1 — имеет предпочтения"
    users ||--|| ratings : "1:1 — имеет рейтинг"
    profiles ||--o{ photos : "1:N — содержит фото (макс 5)"
    users ||--o{ swipes : "1:N — делает свайпы"
    users ||--o{ matches : "1:N — участвует в мэтчах (user1)"
    users ||--o{ matches : "1:N — участвует в мэтчах (user2)"
    users ||--o{ referrals : "1:N — приглашает (referrer)"
    users ||--o| referrals : "1:1 — приглашён (referred)"
```

---

## Подробное описание таблиц

### 1. `users` — Пользователи

> Базовая сущность. Создаётся при первом `/start` в Telegram.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | Внутренний ID |
| `telegram_id` | `BIGINT` | `UNIQUE NOT NULL` | Telegram ID пользователя |
| `username` | `VARCHAR(255)` | `NULLABLE` | Telegram username |
| `referral_code` | `VARCHAR(32)` | `UNIQUE NOT NULL` | Уникальный реферальный код |
| `referred_by` | `INTEGER` | `FK → users(id), NULLABLE` | Кто пригласил |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Активен ли аккаунт |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата регистрации |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата последнего обновления |
| `last_active` | `TIMESTAMP` | `DEFAULT NOW()` | Время последней активности |

<details>
<summary>📑 Индексы</summary>

| Имя | Поля | Тип | Назначение |
|:----|:-----|:----|:-----------|
| `idx_users_telegram_id` | `telegram_id` | UNIQUE | Основной поиск по Telegram ID |
| `idx_users_referral_code` | `referral_code` | UNIQUE | Поиск по реферальному коду |
| `idx_users_is_active` | `is_active` | B-tree | Фильтрация активных пользователей |

</details>

---

### 2. `profiles` — Анкеты

> Данные анкеты: имя, возраст, пол, город, описание, интересы. Связь 1:1 с `users`.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | ID анкеты |
| `user_id` | `INTEGER` | `FK → users(id), UNIQUE NOT NULL` | Владелец (1:1) |
| `name` | `VARCHAR(100)` | `NOT NULL` | Имя |
| `age` | `SMALLINT` | `NOT NULL, CHECK(18..100)` | Возраст |
| `gender` | `VARCHAR(20)` | `NOT NULL` | Пол (`male` / `female` / `other`) |
| `city` | `VARCHAR(100)` | `NOT NULL` | Город |
| `bio` | `TEXT` | `NULLABLE` | О себе (до 500 символов) |
| `interests` | `TEXT[]` | `NULLABLE` | Массив интересов |
| `is_complete` | `BOOLEAN` | `DEFAULT FALSE` | Полностью ли заполнена анкета |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата создания |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата обновления |

<details>
<summary>📑 Индексы</summary>

| Имя | Поля | Тип | Назначение |
|:----|:-----|:----|:-----------|
| `idx_profiles_user_id` | `user_id` | UNIQUE | Поиск анкеты по пользователю |
| `idx_profiles_gender` | `gender` | B-tree | Фильтрация по полу |
| `idx_profiles_city` | `city` | B-tree | Фильтрация по городу |
| `idx_profiles_age` | `age` | B-tree | Фильтрация по возрасту |
| `idx_profiles_filter` | `gender, city, age` | Composite | Основной фильтр ранжирования |

</details>

---

### 3. `photos` — Фотографии

> Фотографии анкеты. Файлы хранятся в MinIO (S3), в БД только ключи.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | ID фото |
| `profile_id` | `INTEGER` | `FK → profiles(id), NOT NULL` | Анкета-владелец |
| `s3_key` | `VARCHAR(512)` | `NOT NULL` | Ключ объекта в S3 (MinIO) |
| `s3_bucket` | `VARCHAR(100)` | `NOT NULL, DEFAULT 'photos'` | Бакет в S3 |
| `is_primary` | `BOOLEAN` | `DEFAULT FALSE` | Главное фото (аватар) |
| `upload_order` | `SMALLINT` | `NOT NULL` | Порядок отображения |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата загрузки |

> **Ограничения:** макс. 5 фотографий на анкету, ровно одно `is_primary = TRUE`

---

### 4. `preferences` — Предпочтения поиска

> Настройки фильтра: кого ищу по полу, возрасту, городу.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | ID |
| `user_id` | `INTEGER` | `FK → users(id), UNIQUE NOT NULL` | Владелец (1:1) |
| `target_gender` | `VARCHAR(20)` | `NOT NULL` | Кого ищу (`male` / `female` / `any`) |
| `age_min` | `SMALLINT` | `DEFAULT 18, CHECK(≥ 18)` | Мин. возраст |
| `age_max` | `SMALLINT` | `DEFAULT 100, CHECK(≤ 100)` | Макс. возраст |
| `city` | `VARCHAR(100)` | `NULLABLE` | Город поиска (`NULL` = любой) |
| `max_distance` | `INTEGER` | `NULLABLE` | Макс. расстояние в км (на будущее) |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата создания |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата обновления |

---

### 5. `swipes` — Свайпы (лайки / пропуски)

> Каждый свайп — одна запись. Уникальность на пару `(swiper, swiped)`.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | ID свайпа |
| `swiper_id` | `INTEGER` | `FK → users(id), NOT NULL` | Кто свайпнул |
| `swiped_id` | `INTEGER` | `FK → users(id), NOT NULL` | Кого свайпнули |
| `action` | `VARCHAR(10)` | `NOT NULL, CHECK('like','skip')` | Действие |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Время свайпа |

<details>
<summary>📑 Индексы</summary>

| Имя | Поля | Тип | Назначение |
|:----|:-----|:----|:-----------|
| `idx_swipes_pair` | `swiper_id, swiped_id` | UNIQUE | Один свайп на пару |
| `idx_swipes_swiped` | `swiped_id` | B-tree | Подсчёт лайков/пропусков |
| `idx_swipes_action` | `action` | B-tree | Фильтрация по типу |
| `idx_swipes_created` | `created_at` | B-tree | Временные запросы для рейтинга |

</details>

---

### 6. `matches` — Мэтчи (взаимные лайки)

> Создаётся при обнаружении взаимного лайка. `user1_id < user2_id` для уникальности.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | ID мэтча |
| `user1_id` | `INTEGER` | `FK → users(id), NOT NULL` | Первый пользователь (меньший ID) |
| `user2_id` | `INTEGER` | `FK → users(id), NOT NULL` | Второй пользователь (больший ID) |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Активен ли мэтч |
| `chat_initiated` | `BOOLEAN` | `DEFAULT FALSE` | Начат ли диалог |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Время мэтча |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | Последнее обновление |

<details>
<summary>📑 Индексы</summary>

| Имя | Поля | Тип | Назначение |
|:----|:-----|:----|:-----------|
| `idx_matches_pair` | `user1_id, user2_id` | UNIQUE | Один мэтч на пару |
| `idx_matches_user1` | `user1_id` | B-tree | Поиск мэтчей пользователя |
| `idx_matches_user2` | `user2_id` | B-tree | Поиск мэтчей пользователя |

</details>

---

### 7. `ratings` — Рейтинги

> Отдельная таблица с рейтингами. Пересчитывается Celery-задачами.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | ID записи |
| `user_id` | `INTEGER` | `FK → users(id), UNIQUE NOT NULL` | Пользователь |
| `primary_score` | `FLOAT` | `DEFAULT 0.0` | Первичный рейтинг (0–100) |
| `profile_completeness` | `FLOAT` | `DEFAULT 0.0` | Полнота анкеты (0–1) |
| `photo_count_score` | `FLOAT` | `DEFAULT 0.0` | Балл за кол-во фото (0–1) |
| `behavioral_score` | `FLOAT` | `DEFAULT 0.0` | Поведенческий рейтинг (0–100) |
| `likes_received` | `INTEGER` | `DEFAULT 0` | Всего лайков получено |
| `like_ratio` | `FLOAT` | `DEFAULT 0.0` | Лайки / показы (0–1) |
| `match_ratio` | `FLOAT` | `DEFAULT 0.0` | Мэтчи / лайки (0–1) |
| `chat_initiation_rate` | `FLOAT` | `DEFAULT 0.0` | Начатые диалоги / мэтчи (0–1) |
| `activity_score` | `FLOAT` | `DEFAULT 0.0` | Активность по времени суток (0–1) |
| `combined_score` | `FLOAT` | `DEFAULT 0.0` | **Итоговый комбинированный рейтинг** |
| `referral_bonus` | `FLOAT` | `DEFAULT 0.0` | Бонус за рефералов |
| `last_calculated_at` | `TIMESTAMP` | `NULLABLE` | Время последнего пересчёта |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата создания |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | Дата обновления |

<details>
<summary>📑 Индексы</summary>

| Имя | Поля | Тип | Назначение |
|:----|:-----|:----|:-----------|
| `idx_ratings_user` | `user_id` | UNIQUE | Один рейтинг на пользователя |
| `idx_ratings_score` | `combined_score DESC` | B-tree | Сортировка по рейтингу |
| `idx_ratings_stale` | `last_calculated_at` | B-tree | Выборка устаревших для пересчёта |

</details>

---

### 8. `referrals` — Реферальная система

> Отслеживание приглашений. Один пользователь может быть приглашён только один раз.

| Поле | Тип | Ограничения | Описание |
|:-----|:----|:------------|:---------|
| `id` | `SERIAL` | `PRIMARY KEY` | ID записи |
| `referrer_id` | `INTEGER` | `FK → users(id), NOT NULL` | Пригласивший |
| `referred_id` | `INTEGER` | `FK → users(id), UNIQUE NOT NULL` | Приглашённый |
| `bonus_applied` | `BOOLEAN` | `DEFAULT FALSE` | Бонус начислен |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | Время регистрации реферала |

---

## Формулы рейтинга

### Уровень 1 — Первичный рейтинг (`primary_score`)

```mermaid
graph LR
    subgraph INPUT["📥 Входные данные"]
        F["Заполненные поля<br/>(name, age, gender,<br/>city, bio, interests)"]
        P["Количество фото<br/>(0–5)"]
    end

    subgraph CALC["🧮 Расчёт"]
        PC["profile_completeness<br/>= filled / 6<br/>+ 0.1 если bio заполнено"]
        PH["photo_count_score<br/>= min(photos / 3, 1.0)"]
    end

    subgraph RESULT["📊 Результат"]
        PS["primary_score<br/>= completeness × 60<br/>+ photo_score × 40<br/><b>Диапазон: 0–100</b>"]
    end

    F --> PC
    P --> PH
    PC --> PS
    PH --> PS

    style INPUT fill:#e3f2fd,stroke:#1976d2
    style CALC fill:#fff3e0,stroke:#f57c00
    style RESULT fill:#e8f5e9,stroke:#388e3c
```

### Уровень 2 — Поведенческий рейтинг (`behavioral_score`)

```mermaid
graph LR
    subgraph INPUT["📥 Метрики поведения"]
        LR_["like_ratio<br/>= likes / views"]
        MR["match_ratio<br/>= matches / likes_given"]
        CR["chat_rate<br/>= chats / matches"]
        AS["activity_score<br/>= peak_hours_coeff"]
    end

    subgraph WEIGHTS["⚖️ Веса"]
        W1["× 30"]
        W2["× 30"]
        W3["× 20"]
        W4["× 20"]
    end

    subgraph RESULT["📊 Результат"]
        BS["behavioral_score<br/>= LR×30 + MR×30<br/>+ CR×20 + AS×20<br/><b>Диапазон: 0–100</b>"]
    end

    LR_ --> W1 --> BS
    MR --> W2 --> BS
    CR --> W3 --> BS
    AS --> W4 --> BS

    style INPUT fill:#fce4ec,stroke:#c62828
    style WEIGHTS fill:#fff3e0,stroke:#f57c00
    style RESULT fill:#e8f5e9,stroke:#388e3c
```

### Уровень 3 — Комбинированный рейтинг (`combined_score`)

```mermaid
graph LR
    subgraph SCORES["📥 Рейтинги"]
        PS["primary_score<br/>(0–100)"]
        BS["behavioral_score<br/>(0–100)"]
        RB["referral_bonus<br/>= referrals × 2.0<br/>(макс 10.0)"]
    end

    subgraph FORMULA["🧮 Формула"]
        CALC["combined_score =<br/>primary × <b>0.3</b><br/>+ behavioral × <b>0.7</b><br/>+ referral_bonus"]
    end

    PS -->|"вес 0.3"| CALC
    BS -->|"вес 0.7"| CALC
    RB -->|"бонус"| CALC

    style SCORES fill:#e3f2fd,stroke:#1976d2
    style FORMULA fill:#e8f5e9,stroke:#388e3c
```

---

## Структура Redis-кэша

```mermaid
graph TB
    subgraph REDIS["⚡ Redis"]
        subgraph FEED["Лента анкет"]
            F1["🔑 feed:{telegram_id}<br/>📦 ZSET {profile_id: score, ...}<br/>⏰ TTL: 30 мин"]
            F2["🔑 feed:{telegram_id}:offset<br/>📦 INTEGER (позиция)<br/>⏰ TTL: 30 мин"]
        end

        subgraph PROFILE_CACHE["Кэш профилей"]
            P1["🔑 profile:{user_id}<br/>📦 HASH {name, age, gender,<br/>city, bio, photo_urls}<br/>⏰ TTL: 15 мин"]
        end

        subgraph LOCKS["Блокировки"]
            L1["🔑 rating:recalculate:lock<br/>📦 STRING '1'<br/>⏰ TTL: 60 сек"]
        end
    end

    style REDIS fill:#fbe9e7,stroke:#dc382d
    style FEED fill:#fff3e0,stroke:#f57c00
    style PROFILE_CACHE fill:#e3f2fd,stroke:#1976d2
    style LOCKS fill:#f3e5f5,stroke:#7b1fa2
```
