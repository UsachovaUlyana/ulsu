from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers import registration as reg
from app.fsm import Registration

from tests.dummy_i18n import DummyI18n

i18n = DummyI18n()


class DummyState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data or {}
        self.current_state = None

    async def get_data(self) -> dict:
        return dict(self.data)

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def set_state(self, state) -> None:
        self.current_state = state

    async def clear(self) -> None:
        self.data.clear()
        self.current_state = None


class DummyMessage:
    def __init__(self, text: str = "", user_id: int = 1) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))
        return None


class DummyCallback:
    def __init__(self, data: str, message: DummyMessage, user_id: int = 1) -> None:
        self.data = data
        self.message = message
        self.from_user = SimpleNamespace(id=user_id)
        self.answer_calls = 0

    async def answer(self, *args, **kwargs):
        self.answer_calls += 1
        return None


def test_reg_pref_age_preset_moves_to_search_city(monkeypatch):
    fake_api = SimpleNamespace(
        upsert_preferences=AsyncMock(),
        apply_referral=AsyncMock(),
    )
    monkeypatch.setattr(reg, "api_client", fake_api)

    state = DummyState({"pref_target": "female", "referral_code": "ABC123"})
    msg = DummyMessage(user_id=42)
    call = DummyCallback("age:25:35", msg, user_id=42)

    asyncio.run(reg.reg_pref_age_preset(call, state, i18n))

    fake_api.upsert_preferences.assert_not_awaited()
    fake_api.apply_referral.assert_not_awaited()
    assert state.data["pref_age_min"] == 25
    assert state.data["pref_age_max"] == 35
    assert state.current_state == Registration.pref_search_city
    assert call.answer_calls == 1
    assert any("Где ищешь собеседников?" in text for text, _ in msg.answers)


def test_reg_pref_age_max_custom_moves_to_search_city(monkeypatch):
    fake_api = SimpleNamespace(
        upsert_preferences=AsyncMock(),
        apply_referral=AsyncMock(),
    )
    monkeypatch.setattr(reg, "api_client", fake_api)

    state = DummyState({"pref_target": "any", "pref_age_min": 20})
    msg = DummyMessage(text="30", user_id=7)

    asyncio.run(reg.reg_pref_age_max_custom(msg, state, i18n))

    fake_api.upsert_preferences.assert_not_awaited()
    fake_api.apply_referral.assert_not_awaited()
    assert state.data["pref_age_max"] == 30
    assert state.current_state == Registration.pref_search_city
    assert any("Где ищешь собеседников?" in text for text, _ in msg.answers)


def test_reg_pref_search_city_any_completes(monkeypatch):
    fake_api = SimpleNamespace(
        upsert_preferences=AsyncMock(),
        apply_referral=AsyncMock(),
    )
    monkeypatch.setattr(reg, "api_client", fake_api)

    state = DummyState({"pref_target": "any", "pref_age_min": 20, "pref_age_max": 30})
    msg = DummyMessage(user_id=7)
    call = DummyCallback("scity:any", msg, user_id=7)

    asyncio.run(reg.reg_pref_search_city(call, state, i18n))

    fake_api.upsert_preferences.assert_awaited_once_with(
        7,
        {"target_gender": "any", "age_min": 20, "age_max": 30, "search_city": None},
    )
    fake_api.apply_referral.assert_not_awaited()
    assert state.data == {}
    assert call.answer_calls == 1
    assert any("Анкета готова" in text for text, _ in msg.answers)
