"""Create the project's base package structure."""

from pathlib import Path


PROJECT_DIRECTORIES = (
    "identity",
    "authorization",
    "content",
    "bot",
    "api",
    "infrastructure",
)


def create_project_structure() -> None:
    """Create each project directory with an empty __init__.py file."""
    for directory_name in PROJECT_DIRECTORIES:
        directory = Path(directory_name)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_text("", encoding="utf-8")


if __name__ == "__main__":
    create_project_structure()