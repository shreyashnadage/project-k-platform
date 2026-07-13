"""Brand configuration loader.

Reads brand.yaml and exposes it as a typed config object.
All UI theming (Frappe CSS, PWA theme, API responses) should
derive from this — never hardcode brand values elsewhere.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

BRAND_DIR = Path(__file__).parent
BRAND_YAML = BRAND_DIR / "brand.yaml"


class BrandIdentity(BaseModel):
    name: str
    tagline: str
    logo_full: str
    logo_full_svg: str
    logo_icon: str
    logo_icon_svg: str

    def logo_full_path(self) -> Path:
        return BRAND_DIR / "assets" / self.logo_full

    def logo_icon_path(self) -> Path:
        return BRAND_DIR / "assets" / self.logo_icon


class BrandBackOffice(BaseModel):
    name: str
    short_name: str


class BrandColors(BaseModel):
    cream: str
    navy: str
    navy_muted: str
    navy_elevated: str
    teal: str
    teal_dark: str
    teal_accessible: str
    saffron: str
    amber: str
    error: str

    surface: str
    surface_muted: str
    border: str
    border_strong: str
    text_secondary: str
    text_tertiary: str

    bg_dark: str
    surface_dark: str
    border_dark: str
    text_on_dark: str
    text_secondary_dark: str

    semantic_success: str
    semantic_warning: str
    semantic_danger: str
    semantic_info: str

    chart_series: list[str] = Field(default_factory=list)


class BrandTypography(BaseModel):
    font_ui: str
    font_mono: str
    google_fonts_url: str
    weights: dict[str, int] = Field(default_factory=dict)
    sizes: dict[str, str] = Field(default_factory=dict)


class BrandShape(BaseModel):
    radius_sm: str
    radius_md: str
    radius_lg: str
    radius_xl: str
    border_width: str
    active_nav_bar: str
    shadow_sm: str
    shadow_md: str
    focus_ring: str
    focus_ring_color: str
    focus_ring_offset: str


class BrandConfig(BaseModel):
    identity: BrandIdentity
    back_office: BrandBackOffice
    colors: BrandColors
    typography: BrandTypography
    shape: BrandShape


@lru_cache(maxsize=1)
def load_brand(config_path: Path | None = None) -> BrandConfig:
    path = config_path or BRAND_YAML
    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    return BrandConfig(**raw)


def reset_brand_cache() -> None:
    load_brand.cache_clear()
