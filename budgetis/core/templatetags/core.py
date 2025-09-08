from django import template


register = template.Library()


@register.simple_tag(takes_context=True)
def navactive(context, url_name: str) -> str:
    match = context["request"].resolver_match
    if not match:
        return ""

    # Reconstruire "namespace:url_name" si un namespace existe
    ns = ":".join(match.namespaces)
    current = f"{ns}:{match.url_name}" if ns else match.url_name

    return "active" if current == url_name else ""
