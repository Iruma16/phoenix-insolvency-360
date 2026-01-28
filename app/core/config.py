"""
Sistema de configuración robusto con Pydantic Settings.

Este módulo centraliza toda la configuración del sistema con:
- Validación automática de tipos
- Documentación inline
- Valores por defecto seguros
- Separación por entornos (dev/staging/prod)
"""
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración global de Phoenix Legal.

    Todas las variables se pueden sobrescribir con variables de entorno.
    """

    # =========================================================
    # ENTORNO Y DEPLOYMENT
    # =========================================================

    environment: Literal["development", "staging", "production"] = Field(
        default="development", env="ENVIRONMENT", description="Entorno de ejecución"
    )

    debug: bool = Field(
        default=False, env="DEBUG", description="Modo debug (solo para development)"
    )

    app_name: str = Field(default="Phoenix Legal", env="APP_NAME")

    app_version: str = Field(default="1.0.0", env="APP_VERSION")

    # =========================================================
    # DATABASE
    # =========================================================

    database_url: str = Field(
        default="sqlite:///./runtime/db/phoenix_legal.db",
        env="DATABASE_URL",
        description="URL de conexión a base de datos",
    )

    db_pool_size: int = Field(
        default=10,
        env="DB_POOL_SIZE",
        ge=1,
        le=100,
        description="Tamaño del pool de conexiones (solo PostgreSQL)",
    )

    db_max_overflow: int = Field(
        default=20,
        env="DB_MAX_OVERFLOW",
        ge=0,
        le=100,
        description="Conexiones adicionales permitidas",
    )

    db_pool_timeout: int = Field(
        default=30,
        env="DB_POOL_TIMEOUT",
        ge=1,
        description="Timeout para obtener conexión del pool (segundos)",
    )

    # =========================================================
    # OPENAI / LLM
    # =========================================================

    openai_api_key: Optional[str] = Field(
        default=None,
        env="OPENAI_API_KEY",
        description="API key de OpenAI (opcional, sistema funciona sin ella)",
    )

    llm_enabled: bool = Field(
        default=True, env="LLM_ENABLED", description="Habilitar/deshabilitar LLM globalmente"
    )

    primary_model: str = Field(
        default="gpt-4o-mini", env="PRIMARY_MODEL", description="Modelo LLM principal"
    )

    fallback_model: str = Field(
        default="gpt-3.5-turbo", env="FALLBACK_MODEL", description="Modelo LLM de fallback"
    )

    llm_timeout_seconds: int = Field(
        default=30, env="LLM_TIMEOUT_SECONDS", ge=5, le=120, description="Timeout para llamadas LLM"
    )

    llm_max_retries: int = Field(
        default=2, env="LLM_MAX_RETRIES", ge=0, le=5, description="Reintentos máximos para LLM"
    )

    # =========================================================
    # EMAIL (SMTP) - Gmail
    # =========================================================

    smtp_host: Optional[str] = Field(default=None, env="SMTP_HOST")
    smtp_port: Optional[int] = Field(default=None, env="SMTP_PORT")
    smtp_user: Optional[str] = Field(default=None, env="SMTP_USER")
    smtp_password: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, env="SMTP_USE_TLS")
    mail_from: Optional[str] = Field(default=None, env="MAIL_FROM")

    # =========================================================
    # FASE 2A: EXTRACCIÓN ESTRUCTURADA (Feature Flags)
    # =========================================================

    enable_llm_extraction: bool = Field(
        default=True,
        env="ENABLE_LLM_EXTRACTION",
        description="Habilitar extracción con GPT-4 (facturas, NER legal)",
    )

    enable_gpt_vision: bool = Field(
        default=True,
        env="ENABLE_GPT_VISION",
        description="Habilitar GPT-4 Vision para imágenes/facturas",
    )

    max_llm_calls_per_document: int = Field(
        default=2,
        env="MAX_LLM_CALLS_PER_DOCUMENT",
        ge=0,
        le=10,
        description="Máximo de llamadas LLM por documento (control de coste)",
    )

    # =========================================================
    # EMBEDDINGS
    # =========================================================

    embedding_model: str = Field(
        default="text-embedding-3-large",
        env="EMBEDDING_MODEL",
        description="Modelo de embeddings de OpenAI",
    )

    embedding_batch_size: int = Field(
        default=64,
        env="EMBEDDING_BATCH_SIZE",
        ge=1,
        le=100,
        description="Tamaño de lote para generar embeddings",
    )

    # =========================================================
    # RAG (RETRIEVAL AUGMENTED GENERATION)
    # =========================================================

    rag_top_k: int = Field(
        default=5,
        env="RAG_TOP_K_DEFAULT",
        ge=1,
        le=20,
        description="Número de chunks a recuperar por defecto",
    )

    rag_min_similarity_score: float = Field(
        default=1.5,
        env="RAG_MIN_SIMILARITY_SCORE",
        ge=0.0,
        le=3.0,
        description="Score máximo de distancia L2 permitido",
    )

    rag_weak_response_max_distance: float = Field(
        default=1.3,
        env="RAG_WEAK_RESPONSE_MAX_DISTANCE",
        ge=0.0,
        le=3.0,
        description="Umbral para considerar respuesta débil",
    )

    rag_hallucination_risk_threshold: float = Field(
        default=1.4,
        env="RAG_HALLUCINATION_RISK_THRESHOLD",
        ge=0.0,
        le=3.0,
        description="Umbral de riesgo de alucinación",
    )

    rag_auto_build_embeddings: bool = Field(
        default=True,
        env="RAG_AUTO_BUILD_EMBEDDINGS",
        description="Construir embeddings automáticamente si no existen",
    )

    rag_cache_enabled: bool = Field(
        default=True, env="RAG_CACHE_ENABLED", description="Habilitar caché de consultas RAG"
    )

    rag_cache_ttl_seconds: int = Field(
        default=3600,
        env="RAG_CACHE_TTL_SECONDS",
        ge=60,
        description="Tiempo de vida del caché (segundos)",
    )

    # =========================================================
    # PATHS Y DIRECTORIOS
    # =========================================================

    data_dir: Path = Field(
        default=Path("clients_data"), env="DATA_DIR", description="Directorio raíz de datos"
    )

    logs_dir: Path = Field(
        default=Path("clients_data/logs"), env="LOGS_DIR", description="Directorio de logs"
    )

    vectorstore_dir: Path = Field(
        default=Path("clients_data/_vectorstore"),
        env="VECTORSTORE_DIR",
        description="Directorio de vectorstores",
    )

    cache_dir: Path = Field(
        default=Path("clients_data/_cache"), env="CACHE_DIR", description="Directorio de caché"
    )

    # =========================================================
    # SEGURIDAD
    # =========================================================

    jwt_secret_key: str = Field(
        default="change_this_secret_key_in_production",
        env="JWT_SECRET_KEY",
        description="Clave secreta para JWT",
    )

    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")

    jwt_access_token_expire_minutes: int = Field(
        default=30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES", ge=5, le=1440
    )

    rate_limit_enabled: bool = Field(
        default=True, env="RATE_LIMIT_ENABLED", description="Habilitar rate limiting"
    )

    rate_limit_per_minute: int = Field(
        default=60,
        env="RATE_LIMIT_PER_MINUTE",
        ge=1,
        le=1000,
        description="Requests máximos por minuto",
    )

    # =========================================================
    # LEGAL Y COMPLIANCE
    # =========================================================

    legal_quality_score_block_threshold: int = Field(
        default=60,
        env="LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD",
        ge=0,
        le=100,
        description="Score mínimo para no bloquear conclusiones",
    )

    legal_quality_score_warning_threshold: int = Field(
        default=75,
        env="LEGAL_QUALITY_SCORE_WARNING_THRESHOLD",
        ge=0,
        le=100,
        description="Score mínimo para no mostrar warning",
    )

    # =========================================================
    # OBSERVABILIDAD
    # =========================================================

    metrics_enabled: bool = Field(
        default=True, env="METRICS_ENABLED", description="Habilitar métricas Prometheus"
    )

    metrics_port: int = Field(
        default=9090,
        env="METRICS_PORT",
        ge=1024,
        le=65535,
        description="Puerto para servidor de métricas",
    )

    tracing_enabled: bool = Field(
        default=False, env="TRACING_ENABLED", description="Habilitar tracing distribuido"
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO", env="LOG_LEVEL")

    log_format: Literal["json", "text"] = Field(
        default="json", env="LOG_FORMAT", description="Formato de logs"
    )

    # =========================================================
    # FEATURE FLAGS (UI/UX)
    # =========================================================

    enable_interactive_charts: bool = Field(
        default=True,
        env="PHOENIX_ENABLE_CHARTS",
        description="Habilitar gráficos interactivos con Plotly (requiere plotly instalado)",
    )

    enable_advanced_filters: bool = Field(
        default=True,
        env="PHOENIX_ENABLE_FILTERS",
        description="Habilitar filtros avanzados en Timeline y Patrones",
    )

    enable_drill_down: bool = Field(
        default=True,
        env="PHOENIX_ENABLE_DRILLDOWN",
        description="Habilitar drill-down interactivo en gráficos",
    )

    # =========================================================
    # VALIDACIONES CUSTOM
    # =========================================================

    @validator("database_url")
    def validate_database_url(cls, v):
        """Valida formato de URL de base de datos."""
        if not v.startswith(("sqlite:///", "postgresql://", "postgresql+psycopg2://")):
            raise ValueError(
                "database_url debe empezar con sqlite:///, postgresql:// o postgresql+psycopg2://"
            )
        return v

    @validator("jwt_secret_key")
    def validate_jwt_secret(cls, v, values):
        """Valida que JWT secret no sea el default en producción."""
        if (
            values.get("environment") == "production"
            and v == "change_this_secret_key_in_production"
        ):
            raise ValueError("JWT_SECRET_KEY debe ser cambiada en producción")
        return v

    @validator("debug")
    def validate_debug(cls, v, values):
        """Debug debe estar deshabilitado en producción."""
        if values.get("environment") == "production" and v:
            raise ValueError("DEBUG debe estar deshabilitado en producción")
        return v

    @validator("data_dir", "logs_dir", "vectorstore_dir", "cache_dir")
    def validate_directories(cls, v):
        """Convierte strings a Path si es necesario."""
        if isinstance(v, str):
            return Path(v)
        return v

    # =========================================================
    # PROPIEDADES COMPUTADAS
    # =========================================================

    @property
    def is_production(self) -> bool:
        """Verifica si está en producción."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Verifica si está en desarrollo."""
        return self.environment == "development"

    @property
    def llm_available(self) -> bool:
        """Verifica si LLM está disponible."""
        return self.llm_enabled and self.openai_api_key is not None

    @property
    def uses_postgres(self) -> bool:
        """Verifica si usa PostgreSQL."""
        return self.database_url.startswith("postgresql")

    # =========================================================
    # CONFIGURACIÓN DE PYDANTIC
    # =========================================================

    # Pydantic v2 (pydantic-settings): permitir variables extra en `.env`
    # (ej: PHOENIX_API_BASE_URL es usada por la UI, pero no es crítica para la API).
    model_config = SettingsConfigDict(
        # Usar ruta absoluta para que funcione independientemente del cwd
        # (p.ej. cuando se ejecuta via uvicorn desde otro directorio).
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        validate_assignment=True,
        extra="ignore",
    )


# =========================================================
# INSTANCIA GLOBAL (SINGLETON)
# =========================================================

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Obtiene la instancia global de configuración (singleton).

    Returns:
        Settings: Configuración global validada
    """
    global _settings

    if _settings is None:
        _settings = Settings()
        # Asegurar compatibilidad con librerías que leen OPENAI_API_KEY de env (OpenAI SDK).
        if _settings.openai_api_key and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = _settings.openai_api_key

    return _settings


# Atajo para importación
settings = get_settings()


# =========================================================
# HELPERS
# =========================================================


def reload_settings() -> Settings:
    """
    Recarga la configuración (útil para tests).

    Returns:
        Settings: Nueva instancia de configuración
    """
    global _settings
    _settings = None
    return get_settings()


def print_config() -> None:
    """Imprime configuración actual (sin secrets)."""
    config = get_settings()

    print("\n" + "=" * 60)
    print("PHOENIX LEGAL - CONFIGURACIÓN")
    print("=" * 60)
    print(f"Environment:     {config.environment}")
    print(f"Debug:           {config.debug}")
    print(f"Version:         {config.app_version}")
    print(f"Database:        {config.database_url.split('/')[-1]}")  # Solo nombre
    print(f"LLM Available:   {config.llm_available}")
    print(f"LLM Model:       {config.primary_model if config.llm_available else 'N/A'}")
    print(f"RAG Cache:       {config.rag_cache_enabled}")
    print(f"Metrics:         {config.metrics_enabled}")
    print(f"Rate Limiting:   {config.rate_limit_enabled}")
    print(f"Log Level:       {config.log_level}")
    print(f"Log Format:      {config.log_format}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # Test de carga
    print_config()
