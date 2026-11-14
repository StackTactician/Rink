"""Exception types for the service layer."""


class RinkError(Exception):
    """Base class for recoverable failures."""


class FetchError(RinkError):
    """An upstream request failed."""


class ResolveError(RinkError):
    """A download link could not be resolved to a direct file URL."""


class DownloadError(RinkError):
    """curl failed to transfer a resolved file."""


#: the old name, for anything outside this repo that caught it
NkiriError = RinkError
