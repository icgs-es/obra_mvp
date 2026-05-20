from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter
def money_es(value):
    """
    Formatea importes en formato español:
    514994.04 -> 514.994,04 €
    -126963.48 -> -126.963,48 €
    """
    if value is None or value == "":
        value = Decimal("0")

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value

    formatted = f"{amount:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


@register.filter
def money_abs_es(value):
    """
    Formatea importes en valor absoluto:
    -5154.03 -> 5.154,03 €
    336.61 -> 336,61 €
    """
    if value is None or value == "":
        value = Decimal("0")

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value

    return money_es(abs(amount))
