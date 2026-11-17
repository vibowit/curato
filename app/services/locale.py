import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("movie_recommend.services.locale")

DEFAULT_LOCALE = "pl"


class LocaleService:
    """Service responsible for discovering, loading, validating and serving

    localized strings, prompt templates and metadata for multiple languages.
    Supports built-in locales (locales/) and user-defined locales (data/locales/).
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        custom_locale_dirs: Optional[List[Path]] = None,
    ):
        if base_dir is not None:
            self.base_dir = base_dir
        else:
            # Root project dir is 2 levels up from app/services/locale.py
            self.base_dir = Path(__file__).resolve().parent.parent.parent

        self.builtin_dir = self.base_dir / "locales"
        self.user_dir = self.base_dir / "data" / "locales"

        self.custom_dirs: List[Path] = custom_locale_dirs or []
        self._locales_cache: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def _get_search_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        if self.builtin_dir.is_dir():
            dirs.append(self.builtin_dir)
        if self.user_dir.is_dir():
            dirs.append(self.user_dir)
        for cdir in self.custom_dirs:
            if cdir.is_dir() and cdir not in dirs:
                dirs.append(cdir)
        return dirs

    def reload(self) -> None:
        """Discovers and reloads all valid JSON locale files from search directories."""
        loaded: Dict[str, Dict[str, Any]] = {}

        for directory in self._get_search_dirs():
            for json_path in directory.glob("*.json"):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    code = data.get("code")
                    if not code or not isinstance(code, str):
                        logger.warning(
                            "Skipping locale file %s: missing string 'code' field", json_path
                        )
                        continue
                    # Overwrite or register locale
                    loaded[code.lower()] = data
                except Exception as e:
                    logger.warning("Failed to load locale file %s: %s", json_path, e)

        self._locales_cache = loaded

    def list_languages(self) -> List[Dict[str, str]]:
        """Returns a list of available languages with code, name, and flag."""
        self.reload()
        result: List[Dict[str, str]] = []
        for code, data in self._locales_cache.items():
            result.append(
                {
                    "code": code,
                    "name": data.get("name", code),
                    "flag": data.get("flag", "🌐"),
                }
            )

        # Place DEFAULT_LOCALE first, then alphabetical by code
        result.sort(key=lambda item: (0 if item["code"] == DEFAULT_LOCALE else 1, item["code"]))
        return result

    def get_locale(self, language_code: Optional[str] = None) -> Dict[str, Any]:
        """Returns the full locale dictionary for the given code.

        Falls back to DEFAULT_LOCALE for missing locale or missing dictionary keys.
        """
        code = (language_code or DEFAULT_LOCALE).lower()
        base_data = self._locales_cache.get(DEFAULT_LOCALE, {})

        if code not in self._locales_cache:
            logger.info(
                "Requested locale '%s' not found, falling back to '%s'", code, DEFAULT_LOCALE
            )
            target_data = base_data
        else:
            target_data = self._locales_cache[code]

        # Merge with fallback base_data for missing keys in ui and prompts
        merged = dict(target_data)
        merged["ui"] = dict(base_data.get("ui", {}))
        merged["ui"].update(target_data.get("ui", {}))

        base_prompts = base_data.get("prompts", {})
        target_prompts = target_data.get("prompts", {})
        merged_prompts: Dict[str, Any] = {}
        for section, values in base_prompts.items():
            merged_prompts[section] = dict(values)
            if section in target_prompts:
                merged_prompts[section].update(target_prompts[section])
        for section, values in target_prompts.items():
            if section not in merged_prompts:
                merged_prompts[section] = dict(values)
        merged["prompts"] = merged_prompts

        return merged

    def get_tmdb_language(self, language_code: Optional[str] = None) -> str:
        """Returns the TMDB language code (e.g. 'pl-PL' or 'en-US') for the specified locale."""
        locale = self.get_locale(language_code)
        return locale.get("tmdb_language", "pl-PL")

    def get_prompt_templates(self, language_code: Optional[str] = None) -> Dict[str, Any]:
        """Returns the prompt template dictionary for the specified locale."""
        locale = self.get_locale(language_code)
        return locale.get("prompts", {})


locale_service = LocaleService()
