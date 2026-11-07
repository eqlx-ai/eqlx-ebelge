from datetime import date
from decimal import Decimal

import pytest

from eqlx_ebelge.synthetic import InvoiceSpec, Item

D = Decimal
SUPPLIER = "4477127820"  # valid check digit, made up
CUSTOMER = "1234567808"  # valid check digit, made up


@pytest.fixture
def spec() -> InvoiceSpec:
    return InvoiceSpec(
        number="EQX2026000000001",
        issue_date=date(2026, 10, 4),
        supplier_vkn=SUPPLIER,
        supplier_name="Örnek Metal Sanayi A.Ş.",
        customer_id=CUSTOMER,
        customer_name="Deneme Yapı Ltd. Şti.",
        uuid="3F2504E0-4F89-41D3-9A0C-0305E82C3301",
        items=[
            Item("Çelik profil", D(10), D("185.40")),  # 1854.00 + 20% = 370.80
            Item("Montaj", D(1), D(1000), D(20), D(10)),  # 1000 - 100 = 900.00 + 20% = 180.00
        ],
    )
