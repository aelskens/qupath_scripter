from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("qupath_scripter")
except PackageNotFoundError:
    __version__ = "dev"