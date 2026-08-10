"""NestConfig-backed validation Adapter for Setup's bed-count choice."""

from nest import NestConfig, NestConfigError


class NestConfigSetupChoiceAdapter:
    def validate_bed_count(self, bed_count: int) -> int:
        try:
            return int(NestConfig(bed_count=bed_count).bed_count)
        except NestConfigError as error:
            raise ValueError(str(error)) from error


__all__ = ("NestConfigSetupChoiceAdapter",)
