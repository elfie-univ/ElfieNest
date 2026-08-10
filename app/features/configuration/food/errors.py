"""Stable business errors for Food configuration."""


class FoodError(RuntimeError):
    """Base class for Food use-case failures."""


class FoodForbidden(FoodError):
    """The authenticated principal cannot perform the requested Food action."""


class FoodNotFound(FoodError):
    """The requested Food package or Elfie assignment does not exist."""


class FoodConflict(FoodError):
    """The requested mutation conflicts with current Food facts."""


class FoodValidationError(FoodError):
    """The requested Food state violates product rules."""


class FoodUnavailable(FoodError):
    """A technical Food dependency is temporarily unavailable."""


__all__ = (
    "FoodConflict",
    "FoodError",
    "FoodForbidden",
    "FoodNotFound",
    "FoodUnavailable",
    "FoodValidationError",
)
