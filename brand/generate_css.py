"""Generate back-office (Frappe) desk CSS from brand.yaml.

Run this whenever brand.yaml changes:
    python -m brand.generate_css

Outputs:
    brand/generated/desk.css       — hook via app_include_css
    brand/generated/portal.css     — hook via web_include_css
    brand/generated/head_fonts.html — inject into Website Theme <head>
"""

from __future__ import annotations

from pathlib import Path

from brand.brand import load_brand

OUTPUT_DIR = Path(__file__).parent / "generated"


def generate_desk_css() -> str:
    b = load_brand()
    c = b.colors
    s = b.shape
    t = b.typography

    return f"""\
/* ==========================================================================
   {b.identity.name} Desk Theme — AUTO-GENERATED from brand.yaml
   Do not edit manually. Run: python -m brand.generate_css
   ========================================================================== */

:root {{
  /* ── Brand tokens ─────────────────────────────────────── */
  --brand-cream: {c.cream};
  --brand-navy: {c.navy};
  --brand-navy-muted: {c.navy_muted};
  --brand-navy-elevated: {c.navy_elevated};
  --brand-teal: {c.teal};
  --brand-teal-dark: {c.teal_dark};
  --brand-teal-accessible: {c.teal_accessible};
  --brand-saffron: {c.saffron};
  --brand-amber: {c.amber};
  --brand-error: {c.error};
  --brand-surface: {c.surface};
  --brand-surface-muted: {c.surface_muted};
  --brand-border: {c.border};
  --brand-border-strong: {c.border_strong};
  --brand-text-secondary: {c.text_secondary};
  --brand-text-tertiary: {c.text_tertiary};

  /* ── Shape tokens ─────────────────────────────────────── */
  --brand-radius-sm: {s.radius_sm};
  --brand-radius-md: {s.radius_md};
  --brand-radius-lg: {s.radius_lg};
  --brand-radius-xl: {s.radius_xl};
  --brand-shadow-sm: {s.shadow_sm};
  --brand-shadow-md: {s.shadow_md};
  --brand-focus-ring: {s.focus_ring};

  /* ── Map to Frappe CSS variables ──────────────────────── */
  --primary: {c.navy};
  --primary-color: {c.navy};
  --btn-primary: {c.navy};
  --text-color: {c.navy};
  --text-muted: {c.text_secondary};
  --bg-color: {c.cream};
  --fg-color: {c.surface};
  --border-color: {c.border};
  --control-bg: {c.surface};
  --control-bg-on-gray: {c.surface_muted};
  --heading-color: {c.navy};
  --navbar-bg: {c.navy};
  --navbar-color: {c.cream};
  --awesomplete-hover-bg: {c.surface_muted};
  --font-stack: {t.font_ui};
}}

/* ── Links & focus ──────────────────────────────────────── */

a,
.link-content a {{
  color: {c.teal};
}}
a:hover {{
  color: {c.teal_accessible};
}}
.btn:focus,
.form-control:focus {{
  border-color: {c.teal};
  box-shadow: {s.focus_ring};
}}

/* ── Primary button ─────────────────────────────────────── */

.btn-primary,
.btn-primary-dark {{
  background-color: {c.navy};
  border-color: {c.navy};
  color: {c.cream};
  border-radius: {s.radius_md};
}}
.btn-primary:hover {{
  background-color: {c.navy_elevated};
  border-color: {c.navy_elevated};
}}

/* ── Secondary / default ────────────────────────────────── */

.btn-default {{
  background-color: {c.surface};
  border-color: {c.border};
  color: {c.navy};
  border-radius: {s.radius_md};
}}

/* ── Accent / "Co" actions ──────────────────────────────── */

.btn-secondary,
.btn.btn-secondary {{
  background-color: {c.teal};
  border-color: {c.teal};
  color: {c.surface};
  border-radius: {s.radius_md};
}}

/* ── Indicators ─────────────────────────────────────────── */

.indicator-pill.green,
.indicator.green {{
  background: rgba(42, 157, 143, 0.15);
  color: {c.semantic_success};
}}
.indicator-pill.orange,
.indicator.orange,
.indicator-pill.yellow {{
  background: rgba(224, 122, 61, 0.15);
  color: {c.semantic_warning};
}}
.indicator-pill.red,
.indicator.red {{
  background: rgba(196, 92, 74, 0.15);
  color: {c.semantic_danger};
}}

/* ── Forms ──────────────────────────────────────────────── */

.form-section .section-head {{
  color: {c.navy};
  font-weight: {t.weights.get("section_title", 600)};
}}
.form-control,
.frappe-control .control-input {{
  border-radius: {s.radius_md};
  border-color: {c.border};
}}
.frappe-list,
.list-row-container {{
  border-color: {c.border};
}}
.list-row-head {{
  color: {c.text_secondary};
  font-weight: {t.weights.get("label", 500)};
}}

/* ── Sidebar / desk ─────────────────────────────────────── */

.desk-sidebar .standard-sidebar-item.selected {{
  border-left: {s.active_nav_bar} solid {c.teal};
  background: {c.surface_muted};
}}
.module-link.active {{
  color: {c.teal};
}}

/* ── Cards / workspace ──────────────────────────────────── */

.widget.number-widget,
.dashboard-list-item {{
  border-radius: {s.radius_lg};
  border: {s.border_width} solid {c.border};
  background: {c.surface};
}}
.widget-head {{
  color: {c.text_secondary};
  font-weight: {t.weights.get("label", 500)};
}}
.widget-body .number {{
  color: {c.navy};
  font-weight: {t.weights.get("kpi", 700)};
}}

/* ── Loan Management specifics ──────────────────────────── */

.munimco-mono,
.frappe-control[data-fieldtype="Currency"] .control-value,
.frappe-control[data-fieldtype="Float"] .control-value {{
  font-family: {t.font_mono};
  font-variant-numeric: tabular-nums;
}}

/* ── Dark mode ──────────────────────────────────────────── */

[data-theme="dark"],
body.dark {{
  --bg-color: {c.bg_dark};
  --fg-color: {c.surface_dark};
  --text-color: {c.text_on_dark};
  --text-muted: {c.text_secondary_dark};
  --border-color: {c.border_dark};
  --control-bg: {c.surface_dark};
  --navbar-bg: {c.bg_dark};
  --primary: {c.teal_dark};
  --primary-color: {c.teal_dark};
}}
[data-theme="dark"] .btn-primary {{
  background-color: {c.cream};
  color: {c.navy};
  border-color: {c.cream};
}}
"""


def generate_portal_css() -> str:
    b = load_brand()
    c = b.colors
    t = b.typography

    return f"""\
/* ==========================================================================
   {b.identity.name} Portal Theme — AUTO-GENERATED from brand.yaml
   Do not edit manually. Run: python -m brand.generate_css
   ========================================================================== */

:root {{
  --bg-color: {c.cream};
  --fg-color: {c.surface};
  --text-color: {c.navy};
  --primary: {c.navy};
  --primary-color: {c.navy};
  --navbar-bg: {c.navy};
  --navbar-color: {c.cream};
  --border-color: {c.border};
  --font-stack: {t.font_ui};
}}

a {{ color: {c.teal}; }}
a:hover {{ color: {c.teal_accessible}; }}
"""


def generate_head_fonts_html() -> str:
    b = load_brand()
    url = b.typography.google_fonts_url
    return f"""\
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="{url}" rel="stylesheet" />
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    desk_css = OUTPUT_DIR / "desk.css"
    desk_css.write_text(generate_desk_css(), encoding="utf-8")
    print(f"wrote {desk_css}")

    portal_css = OUTPUT_DIR / "portal.css"
    portal_css.write_text(generate_portal_css(), encoding="utf-8")
    print(f"wrote {portal_css}")

    head_html = OUTPUT_DIR / "head_fonts.html"
    head_html.write_text(generate_head_fonts_html(), encoding="utf-8")
    print(f"wrote {head_html}")


if __name__ == "__main__":
    main()
