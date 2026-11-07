"""Exception types for the nkiri service layer."""


class NkiriError(Exception):
    """Base class for recoverable nkiri failures."""


class FetchError(NkiriError):
    """An upstream request failed."""


class ResolveError(NkiriError):
    """A download link could not be resolved to a direct file URL."""


class DownloadError(NkiriError):
    """curl failed to transfer a resolved file."""
