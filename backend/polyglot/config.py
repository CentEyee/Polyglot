from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_model_id(model_id: str) -> str:
    """Token Factory catalog ids are vendor-prefixed (nvidia/...). Accept both forms."""
    mid = (model_id or "").strip()
    if mid and "/" not in mid:
        return f"nvidia/{mid}"
    return mid


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    llm_fast: str = "nvidia/Nemotron-3-Nano-30B-A3B"
    llm_balanced: str = "nvidia/Nemotron-3-Super-120b-a12b"
    llm_deep: str = "nvidia/Nemotron-3-Ultra-550b-a55b"

    tavily_api_key: str = ""
    github_token: str = ""

    workdir: str = "/tmp/polyglot"
    sandbox: str = "local"
    max_parallel_workers: int = 6
    cors_origins: str = "http://localhost:3000"

    @property
    def model_fast(self) -> str:
        return normalize_model_id(self.llm_fast)

    @property
    def model_balanced(self) -> str:
        return normalize_model_id(self.llm_balanced)

    @property
    def model_deep(self) -> str:
        return normalize_model_id(self.llm_deep)


def get_settings() -> Settings:
    return Settings()
