import json
from pathlib import Path

from app.services.locale import LocaleService


def test_list_languages_includes_pl_and_en():
    service = LocaleService()
    languages = service.list_languages()
    codes = [lang["code"] for lang in languages]
    assert "pl" in codes
    assert "en" in codes

    pl_info = next(lang for lang in languages if lang["code"] == "pl")
    assert pl_info["name"] == "Polski"
    assert pl_info["flag"] == "🇵🇱"

    en_info = next(lang for lang in languages if lang["code"] == "en")
    assert en_info["name"] == "English"
    assert en_info["flag"] == "🇬🇧"


def test_get_locale_pl_and_en():
    service = LocaleService()
    pl = service.get_locale("pl")
    assert pl["code"] == "pl"
    assert "brand_title" in pl["ui"]
    assert "taste_profile" in pl["prompts"]

    en = service.get_locale("en")
    assert en["code"] == "en"
    assert "brand_title" in en["ui"]
    assert "taste_profile" in en["prompts"]


def test_get_tmdb_language():
    service = LocaleService()
    assert service.get_tmdb_language("pl") == "pl-PL"
    assert service.get_tmdb_language("en") == "en-US"
    # Unknown fallback
    assert service.get_tmdb_language("nonexistent") == "pl-PL"


def test_get_prompt_templates():
    service = LocaleService()
    prompts_pl = service.get_prompt_templates("pl")
    assert "Jesteś wybitnym" in prompts_pl["taste_profile"]["system_instruction"]
    assert "Polish narrative" in prompts_pl["recommendations"]["reason_instruction"]

    prompts_en = service.get_prompt_templates("en")
    assert "distinguished film critic" in prompts_en["taste_profile"]["system_instruction"]
    assert "English narrative" in prompts_en["recommendations"]["reason_instruction"]


def test_custom_user_locale(tmp_path: Path):
    custom_dir = tmp_path / "custom_locales"
    custom_dir.mkdir()
    de_content = {
        "code": "de",
        "name": "Deutsch",
        "flag": "🇩🇪",
        "tmdb_language": "de-DE",
        "ui": {
            "brand_title": "Simkl Recommender DE",
            # omitted keys should fallback to default (pl or en)
        },
        "prompts": {
            "taste_profile": {
                "system_instruction": "Du bist ein Filmkritiker...",
            }
        },
    }
    (custom_dir / "de.json").write_text(json.dumps(de_content), encoding="utf-8")

    service = LocaleService(custom_locale_dirs=[custom_dir])
    languages = service.list_languages()
    codes = [lang["code"] for lang in languages]
    assert "de" in codes

    de_locale = service.get_locale("de")
    assert de_locale["name"] == "Deutsch"
    assert de_locale["ui"]["brand_title"] == "Simkl Recommender DE"
    # Verify fallback for omitted key
    assert "btn_sync" in de_locale["ui"]
    assert de_locale["tmdb_language"] == "de-DE"


def test_invalid_json_is_skipped(tmp_path: Path):
    custom_dir = tmp_path / "broken_locales"
    custom_dir.mkdir()
    (custom_dir / "broken.json").write_text("{invalid json", encoding="utf-8")

    service = LocaleService(custom_locale_dirs=[custom_dir])
    languages = service.list_languages()
    codes = [lang["code"] for lang in languages]
    assert "broken" not in codes
