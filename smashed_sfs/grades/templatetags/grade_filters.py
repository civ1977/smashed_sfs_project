from django import template

register = template.Library()

@register.filter
def get(dictionary, key):
    """Get value from dictionary by key."""
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def map(dictionary, key):
    """Get value from dictionary by key (alias for get)."""
    if dictionary is None:
        return None
    return dictionary.get(key)

_ORDINALS = {1: '1st', 2: '2nd', 3: '3rd'}

@register.filter
def ordinal_term(term_number):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd' - for "1st/2nd/3rd Term" labels."""
    return _ORDINALS.get(term_number, term_number)