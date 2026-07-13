"""Render user-facing docs from brand.yaml-templated sources.

Templates live in docs/templates/*.md.tmpl with {{PRODUCT_NAME}} and
{{BACK_OFFICE_NAME}} placeholders. This substitutes them from brand.yaml
and writes the rendered .md into docs/ — so changing brand.yaml's
back_office.name and re-running this is the only step needed to update
every doc mention, no manual find/replace.

Run this whenever brand.yaml changes:
    python -m brand.render_docs
"""

from __future__ import annotations

from pathlib import Path

from brand.brand import load_brand

BRAND_DIR = Path(__file__).parent
TEMPLATES_DIR = BRAND_DIR.parent / "docs" / "templates"
DOCS_DIR = BRAND_DIR.parent / "docs"


def render(template_text: str) -> str:
    b = load_brand()
    return template_text.replace("{{PRODUCT_NAME}}", b.identity.name).replace(
        "{{BACK_OFFICE_NAME}}", b.back_office.name
    )


def main() -> None:
    if not TEMPLATES_DIR.exists():
        print(f"No templates dir at {TEMPLATES_DIR}, nothing to render.")
        return

    for tmpl_path in sorted(TEMPLATES_DIR.glob("*.md.tmpl")):
        output_name = tmpl_path.name.removesuffix(".tmpl")
        output_path = DOCS_DIR / output_name
        rendered = render(tmpl_path.read_text(encoding="utf-8"))
        output_path.write_text(rendered, encoding="utf-8")
        print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
