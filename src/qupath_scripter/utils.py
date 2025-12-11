import os
from pathlib import Path
from typing import Any

from jinja2 import Template

TEMPLATES_DIR = Path(os.path.abspath(__file__)).parents[2].joinpath("templates")
SCRIPTS_DIR = Path(os.path.abspath(__file__)).parents[2].joinpath("scripts")


def get_template_from_file(name: str) -> Template:
    """Get a Template object from a template file.

    :param template_name: The path to the template.
    :type template_name: str
    :raises FileNotFoundError: Triggered if the name does not correspond to any of the available templates.
    :return: The Jinja2 loaded template.
    :rtype: Template
    """

    if not (template_path := TEMPLATES_DIR.joinpath(name)).exists():
        raise FileNotFoundError(f"The template, {name}, is not one of the available ones.")

    with open(template_path, "r", encoding="utf-8") as f:
        template = Template(f.read())

    return template


def render_template(template: Template, **kwargs: Any) -> str:
    """Render a given template by providing its arguments.

    :param template: The Jinja2 template to render.
    :type template: Template
    :return: The rendered template.
    :rtype: str
    """

    return template.render(**kwargs)


def save_rendered_template(rendered_template: str, name: str) -> None:
    """Save a given rendered template.

    :param rendered_template: The rendered template to save as a script.
    :type rendered_template: str
    :param name: The name to give to the script.
    :type name: str
    """

    with open(SCRIPTS_DIR.joinpath(name), "w", encoding="utf-8") as fp:
        fp.write(rendered_template)


def get_script_absolute_path(name: str) -> Path:
    """Get the absolute path of a given script.

    :param name: The name of the script.
    :type name: str
    :raises FileNotFoundError: Triggered if the name does not correspond to any of the available scripts.
    :return: The absolute path of the given script.
    :rtype: Path
    """

    if not (script_path := SCRIPTS_DIR.joinpath(name)).exists():
        raise FileNotFoundError(f"The script, {name}, is not one of the available ones.")

    return script_path.absolute()
