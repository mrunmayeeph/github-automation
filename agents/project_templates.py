
from __future__ import annotations

# Built-in project idea pool

BUILTIN_IDEAS: list[dict[str, str]] = [
    {"name": "url-shortener", "description": "A minimal URL shortener with a SQLite backend and REST API."},
    {"name": "weather-cli", "description": "Command-line weather reporter using the Open-Meteo free API."},
    {"name": "note-taker", "description": "Plaintext note manager with full-text search, tags, and Markdown export."},
    {"name": "pomodoro-timer", "description": "Terminal-based Pomodoro timer with session logging."},
    {"name": "csv-transformer", "description": "Batch CSV cleaner and column transformer with a simple DSL."},
    {"name": "expense-tracker", "description": "Personal expense tracker with category budgets and monthly reports."},
    {"name": "password-generator", "description": "Cryptographically secure password generator with strength analysis."},
    {"name": "log-parser", "description": "Structured log parser that emits JSON metrics from common log formats."},
    {"name": "static-site-gen", "description": "Minimal static site generator: Markdown → HTML with Jinja2 templates."},
    {"name": "task-scheduler", "description": "Lightweight cron-like task scheduler with a YAML job definition format."},
    {"name": "file-deduplicator", "description": "Finds and removes duplicate files using SHA-256 checksums."},
    {"name": "readme-generator", "description": "Scaffolds a professional README.md from a project config file."},
    {"name": "markdown-linter", "description": "Custom Markdown linter with configurable rule sets."},
    {"name": "image-renamer", "description": "Batch image renamer using EXIF metadata and configurable naming patterns."},
    {"name": "git-stats", "description": "Aggregates and visualises per-author git commit statistics."},
]

# Starter file templates per language

TEMPLATES: dict[str, dict[str, str]] = {
    "python": {
        "main_file": "main.py",
        "source": """\
\"\"\"
{project_name} — {description}
\"\"\"


def main() -> None:
    print("Hello from {project_name}!")


if __name__ == "__main__":
    main()
""",
        "gitignore": """\
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
build/
dist/
*.egg-info/
.eggs/
.env
.venv
venv/
env/
pip-log.txt

# Testing
.tox/
.coverage
htmlcov/
.pytest_cache/
""",
        "requirements": "# Add your dependencies here\n",
    },
    "javascript": {
        "main_file": "index.js",
        "source": """\
/**
 * {project_name} — {description}
 */

function main() {{
  console.log("Hello from {project_name}!");
}}

main();
""",
        "gitignore": """\
# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.npm
.env
dist/
build/
coverage/
.cache/
""",
        "requirements": '{{\n  "name": "{project_name}",\n  "version": "0.1.0",\n  "description": "{description}",\n  "main": "index.js",\n  "scripts": {{\n    "start": "node index.js"\n  }}\n}}\n',
        "requirements_file": "package.json",
    },
}

README_TEMPLATE = """\
# {project_name}

> {description}

## Overview

This project was generated automatically as a starter scaffold.
Replace this section with your own project documentation.

## Getting Started

### Prerequisites

{prerequisites}

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd {project_name}

{install_steps}
```

## Usage

```bash
{run_command}
```

## Project Structure

```
{project_name}/
├── {main_file}       # Application entry point
├── {deps_file}       # Project dependencies
├── .gitignore        # Git ignore rules
└── README.md         # This file
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first.

## License

[MIT](https://choosealicense.com/licenses/mit/)
"""

PREREQS = {
    "python": "- Python 3.10+\n- pip",
    "javascript": "- Node.js 18+\n- npm",
}

INSTALL_STEPS = {
    "python": "pip install -r requirements.txt",
    "javascript": "npm install",
}

RUN_COMMANDS = {
    "python": "python main.py",
    "javascript": "npm start",
}

DEPS_FILES = {
    "python": "requirements.txt",
    "javascript": "package.json",
}


def render_readme(project_name: str, description: str, language: str) -> str:
    lang = language.lower()
    main_file = TEMPLATES[lang]["main_file"]
    return README_TEMPLATE.format(
        project_name=project_name,
        description=description,
        prerequisites=PREREQS.get(lang, ""),
        install_steps=INSTALL_STEPS.get(lang, ""),
        run_command=RUN_COMMANDS.get(lang, ""),
        main_file=main_file,
        deps_file=DEPS_FILES.get(lang, ""),
    )


def render_source(project_name: str, description: str, language: str) -> str:
    lang = language.lower()
    template = TEMPLATES[lang]["source"]
    return template.format(project_name=project_name, description=description)


def render_gitignore(language: str) -> str:
    lang = language.lower()
    return TEMPLATES[lang]["gitignore"]


def render_deps_file(project_name: str, description: str, language: str) -> tuple[str, str]:
    """Return (filename, content) for the language's dependency file."""
    lang = language.lower()
    tmpl = TEMPLATES[lang]
    filename = tmpl.get("requirements_file", "requirements.txt")
    content = tmpl["requirements"].format(
        project_name=project_name, description=description
    )
    return filename, content