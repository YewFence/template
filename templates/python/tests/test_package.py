from {{PYTHON_PACKAGE}} import __doc__


def test_package_imports() -> None:
    assert __doc__
