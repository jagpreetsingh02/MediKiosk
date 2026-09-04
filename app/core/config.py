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
    #: SQLite stays the default so `pytest` and a cold clone run with no network at all.
    #: The demo and any deployment point this at Supabase — see docs/SUPABASE.md for which
    #: of the two connection strings Supabase offers to use, and why.
    database_url: str = "sqlite+aiosqlite:///./medikiosk.db"
    db_echo: bool = False
    #: Supabase project URL (`https://<ref>.supabase.co`). Used for Storage and for the
    #: preflight check, NOT for SQL: clinical reads and writes go through SQLAlchemy on
    #: `database_url`, per §4 and §23 of the brief.
    supabase_url: str | None = None
    #: The publishable (anon) key. Public by design. Unused by this backend — recorded so
    #: the preflight can prove RLS denies it, which is the check that matters.
    supabase_publishable_key: str | None = None
    #: BACKEND ONLY, and it bypasses RLS completely. Never reaches the browser —
    #: `test_no_supabase_secret_can_reach_the_browser` fails the build if it appears
    #: anywhere under frontend/. Accepts either the modern `sb_secret_…` key or a legacy
    #: service-role JWT.
    supabase_secret_key: str | None = None
    #: Where Supabase publishes the JWKS for its own Auth. Recorded for completeness;
    #: MediKiosk verifies its own mock-ABHA tokens and does not use Supabase Auth (§5).
    supabase_jwks_url: str | None = None
    #: Private bucket for prescription and report images.
    supabase_storage_bucket: str = "medical-documents"
    #: Set when the deployment is meant to be on Supabase. With this on, falling back to
    #: SQLite is a startup failure rather than a silent demo on an empty local file.
    require_supabase: bool = False
    redis_url: str = "redis://localhost:6379/0"
    #: When Redis is unreachable the session store falls back to an in-process dict so the
    #: demo survives a dead container. Never enable this in prod: it is single-worker only.
    session_store_allow_memory_fallback: bool = True

    # --- session lifecycle (Invariant 6) ---
    session_ttl_seconds: int = 3600
    purge_on_submit: bool = True

    # --- LLM (Modules A extraction + C prose smoothing) ---
    groq_api_key: str | None = None
    #: `llama-3.3-70b-versatile` (named in the original brief) was decommissioned by Groq;
    #: the API 404s on it. Verify against GET /openai/v1/models before changing this.
    groq_model: str = "openai/gpt-oss-120b"
    #: Groq hosts Whisper on the same key, which gives real server-side ASR for every
    #: language the kiosk offers — see app/speech/groq_whisper.py.
    groq_asr_model: str = "whisper-large-v3-turbo"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 20.0
    groq_max_retries: int = 4
    groq_retry_base_seconds: float = 1.5
    groq_max_backoff_seconds: float = 30.0
    #: "offline" is the default so a dropped demo network changes nothing. Set to "groq"
    #: (or leave "auto" with a key present) to use the hosted model.
    llm_backend: Literal["auto", "offline", "groq"] = "auto"
    llm_temperature: float = 0.0

    # --- speech (Module A voice) ---
    #: `client` is what the shipped kiosk uses (on-device Web Speech, works offline).
    #: `whisper` is real server-side ASR via Groq for clients that cannot recognise locally.
    speech_backend: Literal["local", "whisper", "bhashini", "client"] = "local"
    #: Below this ASR confidence the question degrades to touch rather than guessing.
    asr_confidence_threshold: float = 0.62
    bhashini_base_url: str = "https://dhruva-api.bhashini.gov.in/services/inference"
    bhashini_api_key: str | None = None
    bhashini_user_id: str | None = None
    bhashini_pipeline_id: str | None = None
    vosk_model_dir: str | None = None

    # --- documents (Module B) ---
    #: Only consulted when a caller names an engine explicitly. Every patient upload is
    #: routed by what the file IS — see `documents/backends.py::_chain`.
    ocr_backend: Literal["textlayer", "tesseract", "trocr"] = "textlayer"
    #: Anything at or below this goes to the handwriting lane and is never auto-merged.
    ocr_low_confidence_threshold: float = 0.72
    max_upload_bytes: int = 20 * 1024 * 1024
    #: Re-read the ambiguous lines with Tesseract and let disagreement cost confidence. Costs
    #: one subprocess per ambiguous line, and only ever moves a line *toward* verification.
    ocr_corroborate: bool = True

    # --- handwriting OCR (Module B, the TrOCR lane) ---
    #: The master switch. Off, `trocr` reports itself unavailable and every photograph goes
    #: to Tesseract — which is exactly what happens anyway when torch is not installed, so
    #: this is for turning the model off on a machine that *could* run it.
    handwriting_ocr_enabled: bool = True
    #: A TrOCR fine-tune on handwritten prescription lines. Verify a replacement reads single
    #: LINES, not pages: a page-level model fails by returning one fluent line, silently.
    trocr_model_id: str = "khedim/Medical-Prescription-OCR"
    #: Used only when the fine-tune ships weights without tokenizer/image-processor configs,
    #: which community checkpoints routinely do — the khedim repo has no
    #: `preprocessor_config.json`, so its image processor always comes from here.
    trocr_processor_id: str = "microsoft/trocr-base-handwritten"
    #: Last resort for the tokenizer half. TrOCR's decoder is RoBERTa and shares its
    #: vocabulary, and unlike the TrOCR checkpoints this one publishes a `tokenizer.json`,
    #: which recent transformers releases require.
    trocr_tokenizer_id: str = "roberta-base"
    #: A Hugging Face access token. `khedim/Medical-Prescription-OCR` is a GATED repo: without
    #: a token that has been granted access, the download 401s and the kiosk falls back to
    #: Tesseract. Never logged — see `docs/adr/ADR-0013`.
    hf_token: str | None = None
    trocr_device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    trocr_batch_size: int = 8
    #: One prescription line. Well above the longest real one; a cap this low is also what
    #: bounds the cost of a decoder that has started to loop.
    trocr_max_new_tokens: int = 64
    #: A page segmenting into more bands than this is not a prescription — it is a texture.
    #: Refusing sends it to Tesseract in one pass instead of running hundreds of inferences.
    trocr_max_lines: int = 60
    #: Below this the model is guessing at strokes. The line is dropped, not recorded as
    #: unreliable text: an invented medicine name in the verification lane is still an
    #: invented medicine name on a physician's screen.
    trocr_min_line_confidence: float = 0.35
    #: The fraction of segmented lines the model must actually return text for before the
    #: page is trusted. Below it the page goes to Tesseract *whole*, because a prescription
    #: read in part is a prescription with medicines silently missing — and nothing
    #: downstream can see the gap. See the guard in `trocr.py::_read_page`.
    trocr_min_line_yield: float = 0.6
    #: Matches `documents/render.py::RENDER_DPI`, so the boxes the physician sees were
    #: measured against the image the physician is looking at.
    trocr_render_dpi: int = 200

    # --- prescription interpretation (Module B, stage 9) ---
    #: Auto-correct a misread medicine name only at or above this similarity. Calibrated on
    #: the worked example: "Augmtin" scores 0.875 against Augmentin, which is the weakest
    #: correction still obviously right to a pharmacist. Measured, not guessed — and measured
    #: against the adversarial sweep in tests/test_prescription_interpretation.py, which
    #: mutates every name in the dictionary and asserts none of them auto-corrects to a
    #: DIFFERENT medicine.
    rx_name_auto_similarity: float = 0.86
    #: …and only when it beats the best *different* drug by this much. Without a margin,
    #: "Amlo" would auto-correct to Amlodipine at 0.90 while Amoxicillin sat at 0.89.
    rx_name_margin: float = 0.06
    #: …and only when the recogniser was reasonably sure of the characters. A strong match on
    #: characters nobody read confidently is a strong match on a guess.
    rx_name_min_ocr_confidence: float = 0.55
    #: Below this, not even worth showing as a suggestion.
    rx_name_candidate_similarity: float = 0.70
    rx_name_candidate_limit: int = 3
    #: An interpretation whose weakest field falls below this goes to a human even when
    #: the name was read perfectly. A confident drug with an uncertain dose is not safe.
    rx_interpretation_confidence_floor: float = 0.75

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
    def is_supabase(self) -> bool:
        return "supabase." in self.database_url

    @property
    def database_backend(self) -> str:
        """A human label for the startup log. Never the URL — that carries the password."""
        if self.is_sqlite:
            return "SQLite (local file)"
        if self.is_supabase:
            pooled = "pooler" in self.database_url
            return f"Supabase PostgreSQL ({'pooled' if pooled else 'direct'})"
        return "PostgreSQL"

    @property
    def database_host(self) -> str:
        """Host only, safe to log. Splitting on `@` is what drops the credentials."""
        if self.is_sqlite:
            return self.database_url.rsplit("/", 1)[-1]
        tail = self.database_url.rsplit("@", 1)[-1]
        return tail.split("/", 1)[0]

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
