from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    name = State()
    age = State()
    gender = State()
    city = State()
    bio = State()
    interests = State()
    photos = State()
    pref_target_gender = State()
    pref_age_min = State()
    pref_age_max = State()
    pref_search_city = State()
    pref_search_city_custom = State()


class Filters(StatesGroup):
    """Editing search filters from main menu (Etap 4)."""
    target_gender = State()
    age_min = State()
    age_max = State()
    search_city = State()
    search_city_custom = State()


class LikesFeed(StatesGroup):
    viewing = State()


class RatePeer(StatesGroup):
    choosing_score = State()
