from decimal import ROUND_HALF_UP
from decimal import Decimal
from decimal import InvalidOperation

from django import template


register = template.Library()


@register.filter
def format_money(value: float | Decimal | None) -> str:
    """
    Format a number with thin non-breaking spaces as thousand separators
    and a dot as decimal separator (if any decimals > 0).
    """
    if value is None:
        return ""

    try:
        value = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (ValueError, TypeError, InvalidOperation):
        return str(value)

    # Split integer and fractional parts
    int_part = int(value)
    frac_part = abs(value - int_part)

    # Format integer part with thin non-breaking space
    int_str = f"{int_part:,}".replace(",", "\u202f")

    if frac_part == 0:
        return int_str
    # Always 2 digits after the dot
    frac_str = f"{frac_part:.2f}"[1:]  # Get ".xx"
    return f"{int_str}{frac_str}"
