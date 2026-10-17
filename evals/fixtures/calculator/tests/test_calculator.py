from src.calculator import add, average, divide


def test_add():
    assert add(2, 3) == 5


def test_divide():
    assert divide(10, 4) == 2.5


def test_average_of_empty_list():
    assert average([]) == 0
