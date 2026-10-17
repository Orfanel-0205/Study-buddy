"""A tiny calculator module used to try out Jarvis."""


def add(a, b):
    return a + b


def divide(a, b):
    """Divide a by b. Raises ZeroDivisionError when b is 0."""
    if b == 0:
        raise ZeroDivisionError("b must not be zero")
    return a / b


def average(numbers):
    return sum(numbers) / len(numbers)
