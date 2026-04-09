"""Tests for registration handlers."""

import pytest
from aiogram import Bot
from aiogram.types import Message, User
from aiogram.fsm.context import FSMContext
from unittest.mock import AsyncMock, patch

from app.fsm import RegistrationForm
from app.handlers.registration import router


@pytest.fixture
def mock_user():
    """Create a mock user."""
    return User(id=12345, is_bot=False, first_name="Test", username="test_user")


@pytest.fixture
def mock_message(mock_user):
    """Create a mock message."""
    message = AsyncMock(spec=Message)
    message.from_user = mock_user
    message.text = "/start"
    message.bot = AsyncMock(spec=Bot)
    return message


@pytest.fixture
def mock_fsm_context():
    """Create a mock FSM context."""
    context = AsyncMock(spec=FSMContext)
    context.get_data = AsyncMock(return_value={})
    context.set_state = AsyncMock()
    context.update_data = AsyncMock()
    return context


@pytest.mark.asyncio
async def test_cmd_start_creates_user(mock_message, mock_fsm_context):
    """Test that /start command creates user and starts FSM."""
    with patch("app.handlers.registration.profile_client") as mock_client:
        mock_client.create_user = AsyncMock(return_value={"id": 1})

        await router.message_handlers[0].callback(mock_message, mock_fsm_context)

        mock_client.create_user.assert_called_once_with(
            telegram_id=12345, username="test_user"
        )
        mock_fsm_context.set_state.assert_called_once_with(RegistrationForm.name)


@pytest.mark.asyncio
async def test_process_name_valid_input(mock_message, mock_fsm_context):
    """Test processing valid name input."""
    mock_message.text = "Александр"

    # Get the handler for name state
    handler = None
    for h in router.message_handlers:
        if h.filters and hasattr(h.filters[0], 'state') and h.filters[0].state == RegistrationForm.name:
            handler = h
            break

    if handler:
        await handler.callback(mock_message, mock_fsm_context)

        mock_fsm_context.update_data.assert_called_once_with(name="Александр")
        mock_fsm_context.set_state.assert_called_once_with(RegistrationForm.age)


@pytest.mark.asyncio
async def test_process_name_too_short(mock_message, mock_fsm_context):
    """Test processing name that is too short."""
    mock_message.text = "А"

    await router.message_handlers[1].callback(mock_message, mock_fsm_context)

    mock_message.answer.assert_called_once()
    assert "минимум 2 символа" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_process_age_valid(mock_message, mock_fsm_context):
    """Test processing valid age."""
    mock_message.text = "25"

    handler = None
    for h in router.message_handlers:
        if h.filters and hasattr(h.filters[0], 'state') and h.filters[0].state == RegistrationForm.age:
            handler = h
            break

    if handler:
        await handler.callback(mock_message, mock_fsm_context)

        mock_fsm_context.update_data.assert_called_once_with(age=25)
        mock_fsm_context.set_state.assert_called_once_with(RegistrationForm.gender)


@pytest.mark.asyncio
async def test_process_age_invalid(mock_message, mock_fsm_context):
    """Test processing invalid age (not a number)."""
    mock_message.text = "abc"

    await router.message_handlers[2].callback(mock_message, mock_fsm_context)

    mock_message.answer.assert_called_once()
    assert "должен быть числом" in mock_message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_process_age_out_of_range(mock_message, mock_fsm_context):
    """Test processing age out of range."""
    mock_message.text = "15"

    await router.message_handlers[2].callback(mock_message, mock_fsm_context)

    mock_message.answer.assert_called_once()
    assert "от 18 до 100" in mock_message.answer.call_args[0][0]
