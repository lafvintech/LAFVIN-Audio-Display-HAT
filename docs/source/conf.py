# Configuration file for the Sphinx documentation builder.

from pygments.lexers import Python3Lexer
import time

project = "LAFVIN Audio Display HAT"
copyright = "%Y, LAFVIN"
author = "LAFVIN"
source_encoding = "utf-8"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinxcontrib.video",
    "sphinxcontrib.images",
]

images_config = {
    "override_image_directive": True,
    "cache_path": "_images",
    "default_image_width": "100%",
    "default_image_height": "auto",
    "default_show_title": False,
    "download": True,
}

pygments_lexers = {
    "python-repl": Python3Lexer(),
}

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = []

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_logo = "_static/lafvin-logo.png"

html_theme_options = {
    "logo_only": True,
}

html_title = "LAFVIN Audio Display HAT Tutorial"
