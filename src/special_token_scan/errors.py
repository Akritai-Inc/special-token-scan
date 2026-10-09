class ScanError(Exception):
    """Stable reason code. Never include input text in diagnostic messages."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
