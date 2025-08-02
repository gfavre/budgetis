from django import template
from django.utils.safestring import mark_safe


register = template.Library()


@register.filter
def checkmark(value) -> str:
    """
    Returns a green checkmark or a red cross HTML depending on the boolean value.
    """
    if value:
        return mark_safe('<span class="text-success">✔️</span>')
    return mark_safe('<span class="text-danger">❌</span>')
