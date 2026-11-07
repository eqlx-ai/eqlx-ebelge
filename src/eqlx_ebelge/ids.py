"""Turkish tax and identity numbers.

* VKN (vergi kimlik numarası): 10 digits, the last one a check digit computed from the first nine.
* TCKN (T.C. kimlik numarası): 11 digits, the first not zero, the last two check digits.

Both algorithms are public; :func:`vkn_check_digit` and :func:`tckn_check_digits` build valid numbers for
synthetic test data.
"""

from __future__ import annotations

#: The TCKN that e-Arşiv invoices carry for a consumer who did not give an identity number.
PLACEHOLDER_TCKN = "11111111111"


def vkn_check_digit(first9: str) -> int:
    if len(first9) != 9 or not first9.isdigit():
        raise ValueError("first9 must be nine digits")
    total = 0
    for i, ch in enumerate(first9):
        t = (int(ch) + 9 - i) % 10
        v = (t * 2 ** (9 - i)) % 9
        if t != 0 and v == 0:
            v = 9
        total += v
    return (10 - total % 10) % 10


def is_valid_vkn(value: str) -> bool:
    return len(value) == 10 and value.isdigit() and vkn_check_digit(value[:9]) == int(value[9])


def tckn_check_digits(first9: str) -> str:
    if len(first9) != 9 or not first9.isdigit() or first9[0] == "0":
        raise ValueError("first9 must be nine digits not starting with 0")
    d = [int(c) for c in first9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = (sum(d) + d10) % 10
    return f"{d10}{d11}"


def is_valid_tckn(value: str) -> bool:
    return (
        len(value) == 11 and value.isdigit() and value[0] != "0" and tckn_check_digits(value[:9]) == value[9:]
    )


def is_valid_tax_id(value: str) -> bool:
    """A VKN (10 digits) or a TCKN (11 digits) with a correct check digit."""
    return is_valid_vkn(value) if len(value) == 10 else is_valid_tckn(value)
