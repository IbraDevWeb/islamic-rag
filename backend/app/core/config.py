from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Islamic RAG API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    postgres_db: str = "islamic_rag"
    postgres_user: str = "islamic_rag"
    postgres_password: str = "change_me_local_only"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    qdrant_url: str = "http://qdrant:6333"
    qdrant_dense_collection: str = "islamic_rag_dense_e5_v1"

    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dimension: int = 1024
    embedding_batch_size: int = 8
    embedding_cache_dir: str = "/root/.cache/fastembed"

    # Cross-encoder reranking is intentionally local and CPU-oriented. The model
    # itself is registered in app.search.reranker as a quantized ONNX FastEmbed
    # custom model; these settings control only runtime cost and candidate depth.
    reranker_candidate_pool: int = 20
    reranker_batch_size: int = 4
    reranker_threads: int = 4
    reranker_cache_dir: str = "/root/.cache/fastembed"

    # Synthesis remains disabled by default. Enabling it does not promote generated
    # text to evidence: drafts must pass structural citation validation and later a
    # separate semantic entailment gate before they can be considered releasable.
    synthesis_provider: str = "disabled"
    synthesis_ollama_url: str = "http://host.docker.internal:11434"
    synthesis_model: str = "qwen3:8b"
    synthesis_timeout_seconds: float = 180.0
    synthesis_temperature: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
