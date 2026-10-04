import os
import sys
from pathlib import Path


def prepare_runtime():
    sys.dont_write_bytecode = True
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    project_path = str(Path(__file__).resolve().parent)
    if project_path not in sys.path:
        sys.path.insert(0, project_path)
    try:
        import django  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Use Start Trading with Jay.cmd, or install requirements.txt in your Python environment."
        ) from exc
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jayproject.settings")


if __name__ == "__main__":
    prepare_runtime()
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
