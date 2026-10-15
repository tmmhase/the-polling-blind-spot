"""Errors raised when a public dataset cannot be fetched or validated."""


class DownloadError(RuntimeError):
    """Raised when a remote file cannot be fetched or fails schema checks."""
