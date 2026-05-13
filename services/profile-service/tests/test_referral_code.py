from __future__ import annotations

import string

from app.crud import _generate_referral_code


def test_referral_code_length():
    code = _generate_referral_code()
    assert len(code) == 8


def test_referral_code_alphabet_is_safe():
    # No 0/O/1/I/L confusables
    forbidden = set("O0I1L")
    for _ in range(50):
        code = _generate_referral_code()
        assert all(c not in forbidden for c in code)
        assert all(c in string.ascii_uppercase + string.digits for c in code)
