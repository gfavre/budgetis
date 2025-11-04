from decimal import ROUND_HALF_UP
from decimal import Decimal
from decimal import InvalidOperation

from django import template
from django.utils.safestring import mark_safe


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


@register.filter
def percent_diff(actual, budget):
    try:
        if budget == 0:
            return ""
        return round(((actual - budget) / budget) * 100, 1)
    except (TypeError, ZeroDivisionError):
        return ""


@register.filter
def percent_diff_display(diff: float, is_revenue: bool = False) -> str:  # noqa: FBT001
    """
    Return an HTML snippet showing the percentage diff with color and sign.

    Args:
        diff (float): The percentage difference (may be positive, negative, or 0).

    Returns:
        str: HTML string with colored <small> element, or empty string if diff is "" or None.
    """
    if diff in ("", None):
        return ""

    try:
        diff_val = float(diff)
    except (ValueError, TypeError):
        return ""

    if diff_val > 0:
        sign = "+"
        css_class = "text-success" if is_revenue else "text-danger"
    elif diff_val < 0:
        css_class = "text-danger" if is_revenue else "text-success"
        sign = ""
    else:
        css_class = "text-muted"
        sign = ""

    html = f'<small class="{css_class} text-nowrap">({sign}{diff_val:.0f}%)</small>'
    return mark_safe(html)  # noqa: S308
