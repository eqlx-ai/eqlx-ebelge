import random

import pytest

from eqlx_ebelge.ids import (
    is_valid_tax_id,
    is_valid_tckn,
    is_valid_vkn,
    tckn_check_digits,
    vkn_check_digit,
)
from eqlx_ebelge.synthetic import make_tckn, make_vkn


def test_known_valid_tckn():
    # 10000000146 is the widely used test number that satisfies both TCKN rules
    assert is_valid_tckn("10000000146")
    assert tckn_check_digits("100000001") == "46"


def test_tckn_rules():
    assert not is_valid_tckn("10000000147")
    assert not is_valid_tckn("00000000146")  # cannot start with 0
    assert not is_valid_tckn("1000000014")  # too short
    assert not is_valid_tckn("1000000014a")


def test_conftest_numbers_are_valid():
    assert is_valid_vkn("4477127820")
    assert is_valid_vkn("1234567808")
    assert vkn_check_digit("123456780") == 8  # worked by hand: only the 9th digit contributes, 2 -> 10 - 2


def test_generated_numbers_validate_and_any_last_digit_change_fails():
    rng = random.Random(1)
    for _ in range(500):
        v, t = make_vkn(rng), make_tckn(rng)
        assert is_valid_vkn(v) and is_valid_tax_id(v)
        assert is_valid_tckn(t) and is_valid_tax_id(t)
        for k in range(1, 10):
            assert not is_valid_vkn(v[:-1] + str((int(v[-1]) + k) % 10))
            assert not is_valid_tckn(t[:-1] + str((int(t[-1]) + k) % 10))


def test_vkn_catches_most_single_digit_typos():
    rng = random.Random(2)
    caught = total = 0
    for _ in range(300):
        v = make_vkn(rng)
        for pos in range(9):
            for k in range(1, 10):
                typo = v[:pos] + str((int(v[pos]) + k) % 10) + v[pos + 1 :]
                total += 1
                caught += not is_valid_vkn(typo)
    assert caught / total > 0.85


def test_bad_inputs():
    with pytest.raises(ValueError):
        vkn_check_digit("12345")
    with pytest.raises(ValueError):
        tckn_check_digits("012345678")
