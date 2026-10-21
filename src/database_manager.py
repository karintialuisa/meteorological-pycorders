"""Reexporta o gerenciador relacional no nivel superior de src/."""

from src.database.database_manager import *  # noqa: F401,F403
from src.database.database_manager import __all__  # noqa: F401