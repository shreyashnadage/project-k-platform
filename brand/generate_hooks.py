"""Generate the Frappe app's hooks.py metadata from brand.yaml.

hooks.py's app_title/app_description are what ops staff see in Frappe's own
"Installed Apps" list — this keeps that display name in sync with
brand.yaml's back_office.name instead of a hardcoded literal.

Run this whenever brand.yaml changes:
    python -m brand.generate_hooks

Writes directly (in place, not into an "assets" dir) since Frappe requires
hooks.py at the app package root:
    brand/backoffice_app/munimco_brand/hooks.py
"""

from __future__ import annotations

from pathlib import Path

from brand.brand import load_brand

HOOKS_PATH = Path(__file__).parent / "backoffice_app" / "munimco_brand" / "hooks.py"


def generate_hooks_py() -> str:
    b = load_brand()

    return f"""\
# {b.back_office.name} — Frappe Hooks
# AUTO-GENERATED from brand.yaml. Do not edit manually. Run: python -m brand.generate_hooks
# This app re-skins Frappe Desk and portal with the {b.identity.name} brand identity.
# CSS is auto-generated separately from brand/brand.yaml via python -m brand.generate_css.

app_name = "munimco_brand"
app_title = "{b.back_office.name}"
app_publisher = "Project K"
app_description = "{b.identity.name} brand theme for Frappe Desk and portal"
app_version = "0.1.0"

app_include_css = "/assets/munimco_brand/css/desk.css"
web_include_css = "/assets/munimco_brand/css/portal.css"

website_context = {{
    "favicon": "/assets/munimco_brand/images/favicon.png",
    "splash_image": "/assets/munimco_brand/images/logo.png",
}}
"""


def main() -> None:
    HOOKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOKS_PATH.write_text(generate_hooks_py(), encoding="utf-8")
    print(f"wrote {HOOKS_PATH}")


if __name__ == "__main__":
    main()
