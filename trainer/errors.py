"""Stable error codes localized by the browser."""

class AppError(Exception):
    def __init__(self, status: int, code: str, **details):
        super().__init__(code)
        self.status = status
        self.code = code
        self.details = details
