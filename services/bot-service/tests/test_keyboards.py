from __future__ import annotations

from app.keyboards import (
    age_preset_kb,
    distance_kb,
    gender_kb,
    main_menu_kb,
    photos_done_kb,
    swipe_kb,
    target_gender_kb,
)


def test_gender_kb_has_three_options():
    kb = gender_kb()
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert flat == ["gender:male", "gender:female", "gender:other"]


def test_target_gender_kb():
    kb = target_gender_kb()
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert flat == ["tgender:male", "tgender:female", "tgender:any"]


def test_distance_kb_six_options():
    kb = distance_kb()
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert flat == ["dist:5", "dist:10", "dist:25", "dist:50", "dist:100", "dist:0"]


def test_swipe_kb_encodes_target_id():
    kb = swipe_kb(123456789)
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "swipe:like:123456789" in flat
    assert "swipe:skip:123456789" in flat
    assert "swipe:stop" in flat


def test_main_menu_has_required_buttons():
    kb = main_menu_kb()
    texts = [b.text for row in kb.keyboard for b in row]
    assert "🔥 Смотреть анкеты" in texts
    assert "👤 Моя анкета" in texts
    assert "⚙️ Фильтры" in texts
    assert "💌 Мои мэтчи" in texts
    assert "🎁 Пригласить друга" in texts


def test_photos_done_has_done_button():
    kb = photos_done_kb()
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert flat == ["photos:done"]


def test_photos_done_shows_counter_when_nonzero():
    kb = photos_done_kb(3)
    label = kb.inline_keyboard[0][0].text
    assert "3" in label and "5" in label


def test_age_preset_kb_has_custom_option():
    kb = age_preset_kb()
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    # 6 presets + custom
    assert "age:custom" in flat
    assert "age:18:25" in flat
    assert "age:18:99" in flat  # "any"
    assert len(flat) == 7
