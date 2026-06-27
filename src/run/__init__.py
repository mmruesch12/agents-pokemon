__all__ = ["AutonomousRunner"]


def __getattr__(name: str):
    if name == "AutonomousRunner":
        from src.run.autonomous_runner import AutonomousRunner
        return AutonomousRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")