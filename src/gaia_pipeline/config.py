"""Configuration loading: settings, variable catalogue and per-country files."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines into os.environ without overriding existing values."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def expand_env(value: Any) -> Any:
    """Recursively replace ${VAR} / ${VAR:-default} in strings."""
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match) -> str:
        name, default = match.group(1), match.group(2)
        return os.environ.get(name, default if default is not None else "")

    return _ENV_PATTERN.sub(replace, value)


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a YAML mapping.")
    return data


def _check_string_keys(section: dict[str, Any], where: str) -> None:
    bad = [k for k in section if not isinstance(k, str)]
    if bad:
        raise ValueError(
            f"{where}: keys {bad} are not text. Quote YAML keys such as \"no\" "
            "(unquoted no/yes/on/off are read as booleans)."
        )


def parse_date(value: Any, latest: date) -> date:
    if isinstance(value, date):
        return value
    text = str(value).strip().lower()
    if text in ("latest", "", "none"):
        return latest
    if re.fullmatch(r"\d{4}-\d{2}", text):
        text += "-01"
    return date.fromisoformat(text)


@dataclass
class CountryConfig:
    key: str
    name: str
    iso2: str
    iso3: str
    area: list[float]
    admin_level: int
    boundaries: dict[str, Any]
    pollutants: list[str]
    start: date
    end: date
    enabled: bool = True
    path: Path | None = None
    weather: dict[str, Any] = field(default_factory=dict)   # ERA5 settings ({} = off)
    health: dict[str, Any] = field(default_factory=dict)    # DHIS2 file settings ({} = none)


@dataclass
class Settings:
    raw: dict[str, Any]
    variables: dict[str, Any]
    root: Path = REPO_ROOT
    countries: dict[str, CountryConfig] = field(default_factory=dict)

    def path(self, key: str) -> Path:
        path = Path(self.raw["paths"][key])
        return path if path.is_absolute() else self.root / path

    @property
    def database(self) -> dict[str, Any]:
        return self.raw["database"]

    @property
    def copernicus(self) -> dict[str, Any]:
        return self.raw["copernicus"]

    @property
    def load(self) -> dict[str, Any]:
        return self.raw["load"]

    @property
    def available_until(self) -> date:
        return parse_date(self.copernicus.get("available_until", "latest"), date.today())

    @property
    def era5_available_until(self) -> date:
        """Last day of the last month ERA5 fully covers (published ~1 week late)."""
        value = self.raw.get("era5", {}).get("available_until", "latest")
        if str(value).strip().lower() != "latest":
            return parse_date(value, date.today())
        cutoff = date.fromordinal(date.today().toordinal() - 10)
        return date.fromordinal(date(cutoff.year, cutoff.month, 1).toordinal() - 1)


def _validate_country(key: str, data: dict[str, Any], variables: dict[str, Any]) -> None:
    for section in ("country", "area", "boundaries", "pollutants"):
        if section not in data:
            raise ValueError(f"countries/{key}.yml: missing '{section}'")
    for item in ("name", "iso2", "iso3"):
        if not data["country"].get(item):
            raise ValueError(f"countries/{key}.yml: missing country.{item}")
    area = data["area"]
    if len(area) != 4:
        raise ValueError(f"countries/{key}.yml: area must be [N, W, S, E]")
    north, west, south, east = (float(v) for v in area)
    if not (north > south and east > west):
        raise ValueError(f"countries/{key}.yml: area must be [N, W, S, E] with N>S and E>W")
    unknown = [p for p in data["pollutants"] if str(p) not in variables["pollutants"]]
    if unknown:
        raise ValueError(
            f"countries/{key}.yml: unknown pollutant(s) {unknown}. "
            f"Known: {sorted(variables['pollutants'])}"
        )
    level = int(data["boundaries"].get("admin_level", 0))
    if not 1 <= level <= 5:
        raise ValueError(f"countries/{key}.yml: boundaries.admin_level must be 1-5")


def load_country(path: Path, variables: dict[str, Any], latest: date) -> CountryConfig:
    key = path.stem
    data = expand_env(read_yaml(path))
    _validate_country(key, data, variables)
    period = data.get("period", {})
    return CountryConfig(
        key=key,
        name=data["country"]["name"],
        iso2=data["country"]["iso2"].upper(),
        iso3=data["country"]["iso3"].upper(),
        area=[float(v) for v in data["area"]],
        admin_level=int(data["boundaries"]["admin_level"]),
        boundaries=data["boundaries"],
        pollutants=[str(p) for p in data["pollutants"]],
        start=parse_date(period.get("start", "2003-01-01"), latest),
        end=parse_date(period.get("end", "latest"), latest),
        enabled=bool(data.get("enabled", True)),
        path=path,
        weather=data.get("weather") or {},
        health=data.get("health") or {},
    )


def load_settings(config_dir: Path = CONFIG_DIR) -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    raw = expand_env(read_yaml(config_dir / "settings.yml"))
    variables = read_yaml(config_dir / "variables.yml")
    for section in ("pollutants", "meteorology", "weather"):
        _check_string_keys(variables.get(section, {}), f"variables.yml:{section}")
    settings = Settings(raw=raw, variables=variables)
    latest = settings.available_until
    for path in sorted((config_dir / "countries").glob("*.yml")):
        if path.name.startswith("_"):
            continue
        country = load_country(path, variables, latest)
        settings.countries[country.key] = country
    return settings


def select_countries(settings: Settings, names: list[str] | None, all_enabled: bool) -> list[CountryConfig]:
    if all_enabled:
        chosen = [c for c in settings.countries.values() if c.enabled]
        if not chosen:
            raise ValueError("No enabled countries in config/countries/.")
        return chosen
    if not names:
        raise ValueError("Pass --country NAME (repeatable) or --all.")
    lookup: dict[str, CountryConfig] = {}
    for country in settings.countries.values():
        for alias in (country.key, country.name, country.iso2, country.iso3):
            lookup[alias.lower()] = country
    chosen = []
    for name in names:
        country = lookup.get(name.lower())
        if country is None:
            raise ValueError(
                f"Unknown country '{name}'. Configured: {sorted(settings.countries)}"
            )
        chosen.append(country)
    return chosen
