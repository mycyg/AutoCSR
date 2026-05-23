"""Project-level helpers (M12).

Currently exposes only the template loader. Project CRUD remains in
:mod:`app.server.routes.projects` (single source of truth for storage).
"""
from app.projects.templates import (
    ProjectTemplate,
    get_template,
    list_templates,
    template_root,
)

__all__ = [
    "ProjectTemplate",
    "get_template",
    "list_templates",
    "template_root",
]
