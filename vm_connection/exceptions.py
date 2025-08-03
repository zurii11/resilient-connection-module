class ConnectionFailed(Exception):
    """Raised when a connection attempt is failed."""
    pass

class CommandTimeout(Exception):
    """Raised when an SSH command times out."""
    pass

class UnexpectedRebootDetected(Exception):
    """Raised when an unexpected reboot is detected."""
    pass

class BootTimeUnavailable(Exception):
    """Raised when retrieving boot time failed."""
    pass
