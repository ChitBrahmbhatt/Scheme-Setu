"""Loads the JSON data files once at startup (BACKEND_BRIEF.md Step 2).

No database. Five schemes and eighteen partners live in JSON files, loaded
into module-level structures and validated with Pydantic at load time —
a malformed data file fails loudly here rather than at request time.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.data_models import (
    ActivitiesFile,
    CoursesFile,
    DocumentsFile,
    I18nBundle,
    PartnersFile,
    SchemesFile,
)

SUPPORTED_LOCALES = ("en", "hi")


def _default_data_dir() -> Path:
    # backend/app/loader.py -> app -> backend -> repo root -> data/
    return Path(__file__).resolve().parents[2] / "data"


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required data file is missing: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_schemes(data_dir: Path) -> SchemesFile:
    return SchemesFile.model_validate(_read_json(data_dir / "schemes.json"))


def load_partners(data_dir: Path) -> PartnersFile:
    return PartnersFile.model_validate(_read_json(data_dir / "partners.json"))


def load_activities(data_dir: Path) -> ActivitiesFile:
    return ActivitiesFile.model_validate(_read_json(data_dir / "activities.json"))


def load_courses(data_dir: Path) -> CoursesFile:
    return CoursesFile.model_validate(_read_json(data_dir / "courses.json"))


def load_documents(data_dir: Path) -> DocumentsFile:
    return DocumentsFile.model_validate(_read_json(data_dir / "documents.json"))


def load_i18n(data_dir: Path) -> dict[str, I18nBundle]:
    bundles: dict[str, I18nBundle] = {}
    for locale in SUPPORTED_LOCALES:
        path = data_dir / "i18n" / f"{locale}.json"
        bundles[locale] = I18nBundle.from_dict(_read_json(path))

    key_sets = {locale: set(bundle.root.keys()) for locale, bundle in bundles.items()}
    reference_locale = "en"
    reference_keys = key_sets[reference_locale]
    for locale, keys in key_sets.items():
        if keys != reference_keys:
            missing = reference_keys - keys
            extra = keys - reference_keys
            raise ValueError(
                f"i18n bundle '{locale}' does not match '{reference_locale}' key set "
                f"(missing={sorted(missing)}, extra={sorted(extra)})"
            )
    return bundles


@dataclass(frozen=True)
class LoadedData:
    schemes: SchemesFile
    partners: PartnersFile
    activities: ActivitiesFile
    courses: CoursesFile
    documents: DocumentsFile
    i18n: dict[str, I18nBundle]


def load_all(data_dir: Path | None = None) -> LoadedData:
    resolved = data_dir or _default_data_dir()
    return LoadedData(
        schemes=load_schemes(resolved),
        partners=load_partners(resolved),
        activities=load_activities(resolved),
        courses=load_courses(resolved),
        documents=load_documents(resolved),
        i18n=load_i18n(resolved),
    )


@lru_cache(maxsize=1)
def get_data() -> LoadedData:
    """Cached singleton entry point for routers: JSON is parsed and validated
    once per process, on first access."""
    return load_all()
