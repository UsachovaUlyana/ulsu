"""FSM states for profile registration."""

from aiogram.fsm.state import State, StatesGroup


class RegistrationForm(StatesGroup):
    """States for the profile registration FSM."""

    # Step 1: Basic info
    name = State()
    age = State()
    gender = State()
    city = State()

    # Step 2: Extended info
    bio = State()
    interests = State()

    # Step 3: Photos (1-5)
    photos = State()

    # Step 4: Search preferences
    target_gender = State()
    age_min = State()
    age_max = State()
    search_city = State()
