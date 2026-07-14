class UploaderError(Exception):
    """Base user-safe uploader error."""


class ConfigurationError(UploaderError):
    pass


class InsufficientDiskSpace(UploaderError):
    pass


class UploadError(UploaderError):
    pass


class JobCancelled(UploaderError):
    pass

