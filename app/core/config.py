"""Application settings. Everything configurable lives here, nothing is hardcoded elsewhere.

Adapted from the SIH 25026 service (see docs/PORTED.md). The ICD/NAMASTE terminology settings
carry across because the coding sidecar reuses the same closed-vocabulary guard.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Canonical system URLs. Use verbatim; never construct these at a call site.
ICD_MMS_SYSTEM = "http://id.who.int/icd/release/11/mms"
NAMASTE_SYSTEM_BASE = "https://ayush.gov.in/fhir/CodeSystem/namaste"
SNOMED_SYSTEM = "http://snomed.info/sct"
LOINC_SYSTEM = "http://loinc.org"
#: Dashavidha Pariksha parameters. A MediKiosk-local CodeSystem until AYUSH publishes one.
DASHAVIDHA_SYSTEM = "https://medikiosk.local/fhir/CodeSystem/dashavidha-pariksha"
TEST_SYSTEM = "http://example.org/test-cs"  # fixtures ONLY

WHO_ATTRIBUTION = (
    "International Classification of Diseases, Eleventh Revision (ICD-11), "
    "World Health Organization (WHO) 2019/2021, https://icd.who.int/browse11. "
    "Licensed under Creative Commons Attribution-NoDerivatives 3.0 IGO (CC BY-ND 3.0 IGO)."
)

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी",
    "bn": "বাংলা",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "mr": "मराठी",
    "kn": "ಕನ್ನಡ",
    "ml": "മലയാളം",
    "gu": "ગુજરાતી",
    "pa": "ਪੰਜਾਬੀ",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- app ---
    app_name: str = "medikiosk"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- persistence ---
    database_url: str = "sqlite+aiosqlite:///./medikiosk.db"
    db_echo: bool = False
    redis_url: str = "redis://localhost:6379/0"
    #: When Redis is unreachable the session store falls back to an in-process dict so the
    #: demo survives a dead container. Never enable this in prod: it is single-worker only.
    session_store_allow_memory_fallback: bool = True

    # --- session lifecycle (Invariant 6) ---
    session_ttl_seconds: int = 3600
    purge_on_submit: bool = True

    # --- LLM (Modules A extraction + C prose smoothing) ---
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 20.0
    groq_max_retries: int = 2
    #: "offline" is the default so a dropped demo network changes nothing. Set to "groq"
    #: (or leave "auto" with a key present) to use the hosted model.
    llm_backend: Literal["auto", "offline", "groq"] = "auto"
    llm_temperature: float = 0.0

    # --- speech (Module A voice) ---
    speech_backend: Literal["local", "bhashini", "client"] = "local"
    #: Below this ASR confidence the question degrades to touch rather than guessing.
    asr_confidence_threshold: float = 0.62
    bhashini_base_url: str = "https://dhruva-api.bhashini.gov.in/services/inference"
    bhashini_api_key: str | None = None
    bhashini_user_id: str | None = None
    bhashini_pipeline_id: str | None = None
    vosk_model_dir: str | None = None

    # --- documents (Module B) ---
    ocr_backend: Literal["textlayer", "tesseract"] = "textlayer"
    #: Anything at or below this goes to the handwriting lane and is never auto-merged.
    ocr_low_confidence_threshold: float = 0.72
    max_upload_bytes: int = 20 * 1024 * 1024

    # --- terminology (coding sidecar) ---
    namaste_version: str = "1.0"
    icd_release_id: str = "2026-01"
    dashavidha_version: str = "0.1.0"
    terminology_seed_dir: str = "data/terminology"

    # --- auth & policy (Module D) ---
    policy_file: str = "config/policy.yaml"
    auth_required: bool = False
    jwt_secret: str = "dev-only-not-a-real-secret-change-me-in-any-deployment"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "mock-abdm-idp"
    jwt_audience: str = "medikiosk"

    # --- HIS / ABDM push ---
    his_fhir_endpoint: str = "http://localhost:8000/api/v1/stub-his/Bundle"
    his_push_timeout_seconds: float = 15.0

    # --- ontology ---
    ontology_dir: str = "data/ontology"
    ayush_mode_default: bool = False

    namaste_systems: dict[str, str] = Field(
        default_factory=lambda: {
            "ayurveda": f"{NAMASTE_SYSTEM_BASE}-ayurveda",
            "siddha": f"{NAMASTE_SYSTEM_BASE}-siddha",
            "unani": f"{NAMASTE_SYSTEM_BASE}-unani",
        }
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
