"""Errors raised while cleaning polling tables."""


class PreprocessError(Exception):
    """A raw file is missing or does not match the schema this step expects."""
