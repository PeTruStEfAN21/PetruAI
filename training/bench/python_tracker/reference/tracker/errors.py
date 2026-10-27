"""Exception hierarchy of the tracker."""


class TrackerError(Exception):
    """Base class for every error the tracker raises on purpose."""


class NotFoundError(TrackerError):
    """An unknown user, project, issue or label."""


class DuplicateError(TrackerError):
    """Something that must be unique already exists."""


class ValidationError(TrackerError):
    """A value has the wrong shape."""


class TransitionError(TrackerError):
    """The workflow does not allow a status change."""


class CycleError(TrackerError):
    """A dependency would close a cycle; `path` lists the keys around it."""

    def __init__(self, path):
        self.path = list(path)
        super().__init__("dependency cycle: " + " -> ".join(self.path))


class StorageError(TrackerError):
    """The data file cannot be read or has an unsupported schema."""


class QuerySyntaxError(TrackerError):
    """A search query that cannot be parsed; `position` is the offset of the bad token."""

    def __init__(self, message, position=None):
        self.position = position
        super().__init__(message)
