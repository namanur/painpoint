"""Main package for Lean Agent Orchestrator."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = "postgresql:///painpoint"  # Uses peer authentication
    
    # Pool settings (optimized for 4GB RAM VPS)
    pool_min_size: int = 1
    pool_max_size: int = 5
    
    # Validation
    max_retries_default: int = 3
    max_retries_limit: int = 5
    
    model_config = {
        "env_prefix": "PAINPOINT_",
        "env_file": ".env",
        "extra": "ignore"
    }


settings = Settings()
