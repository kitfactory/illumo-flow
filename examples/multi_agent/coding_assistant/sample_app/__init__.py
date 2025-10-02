"""Sample application package for coding assistant demo."""

def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a - b  # intentional bug for the assistant to fix


def multiply(a: int, b: int) -> int:
    """Return the product of two integers."""
    return a * b
