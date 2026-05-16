"""Посев тестовых пользователей для JMeter-нагрузочного теста.

Создаёт пользователей через Profile Service REST API.
Telegram ID выбираются из диапазона 100_000_000–999_999_999
(совпадает с RandomVariableConfig в dating_load_test.jmx).
"""

from __future__ import annotations

import asyncio
import random
import string

import aiohttp

PROFILE_URL = "http://localhost:8001"
NUM_USERS = 200
BATCH_SIZE = 20

CITIES = ["москва", "питер", "казань", "новосибирск", "екатеринбург", "самара"]
INTERESTS_POOL = ["travel", "music", "sport", "food", "books", "movies", "games", "art", "tech", "coffee"]


def random_name(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length)).capitalize()


def make_user(tg_id: int) -> dict:
    gender = random.choice(["male", "female"])
    target = "female" if gender == "male" else "male"
    age = random.randint(18, 35)
    return {
        "telegram_id": tg_id,
        "gender": gender,
        "target": target,
        "age": age,
    }


async def create_user(session: aiohttp.ClientSession, tg_id: int) -> bool:
    try:
        async with session.post(
            f"{PROFILE_URL}/api/v1/users/",
            json={"telegram_id": tg_id, "username": f"test_{tg_id}"},
        ) as resp:
            if resp.status not in (200, 201):
                return False
    except Exception:
        return False
    return True


async def create_profile(session: aiohttp.ClientSession, tg_id: int, data: dict) -> bool:
    payload = {
        "name": random_name(),
        "age": data["age"],
        "gender": data["gender"],
        "city": random.choice(CITIES),
        "bio": f"Test bio for user {tg_id}",
        "interests": random.sample(INTERESTS_POOL, k=random.randint(2, 5)),
    }
    try:
        async with session.put(
            f"{PROFILE_URL}/api/v1/users/{tg_id}/profile",
            json=payload,
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


async def create_preferences(session: aiohttp.ClientSession, tg_id: int, data: dict) -> bool:
    age_min = max(18, data["age"] - random.randint(0, 5))
    age_max = min(100, data["age"] + random.randint(3, 10))
    payload = {
        "target_gender": data["target"],
        "age_min": age_min,
        "age_max": age_max,
        "search_city": random.choice([None, random.choice(CITIES)]),
    }
    try:
        async with session.put(
            f"{PROFILE_URL}/api/v1/users/{tg_id}/preferences",
            json=payload,
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


async def seed_one(session: aiohttp.ClientSession, tg_id: int) -> bool:
    data = make_user(tg_id)
    ok = await create_user(session, tg_id)
    if not ok:
        return False
    ok = await create_profile(session, tg_id, data)
    if not ok:
        return False
    ok = await create_preferences(session, tg_id, data)
    return ok


async def main() -> None:
    # Фиксированный seed для воспроизводимости (telegram_id будут одинаковые между прогонами)
    random.seed(42)
    tg_ids = random.sample(range(100_000_000, 1_000_000_000), k=NUM_USERS)

    created = 0
    failed = 0

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(tg_ids), BATCH_SIZE):
            batch = tg_ids[i : i + BATCH_SIZE]
            results = await asyncio.gather(*(seed_one(session, tid) for tid in batch))
            batch_ok = sum(results)
            created += batch_ok
            failed += len(batch) - batch_ok
            print(f"  Batch {i//BATCH_SIZE + 1}: {batch_ok}/{len(batch)} OK (total {created}/{NUM_USERS})")

    print(f"\nDone. Created: {created}, Failed: {failed}")
    print(f"JMeter теперь может использовать telegram_id из диапазона 100M–999M")


if __name__ == "__main__":
    asyncio.run(main())
