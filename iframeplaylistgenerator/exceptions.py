class GenericError(Exception):
    """
    Generic error
    """
    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self.args)

class BadPlaylistError(GenericError):
    """
    Error raised when the playlist is unusable
    """

class PlaylistLoadError(GenericError):
    """
    Error raised when loading the playlist failed
    """

class DataError(GenericError):
    """
    Error raised when reading transport stream data failed
    """

class DependencyError(GenericError):
    """
    Error raised when a dependency is not installed
    """
