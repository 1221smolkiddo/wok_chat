from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    MESSAGE_TTL_HOURS: int = 48
    CLEANUP_INTERVAL_SECONDS: int = 300
    DB_ECHO: bool = False
    ENVIRONMENT: str = "development"
    FORCE_HTTPS: bool = False
    UPLOAD_DIR: str = "uploads"
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_SECONDS: int = 900
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:8000", "http://localhost:8000"])
    TRUSTED_HOSTS: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])
    USER_ONE_USERNAME: str = "Alice"
    USER_ONE_PASSWORD: str = "alice123"
    USER_TWO_USERNAME: str = "Bob"
    USER_TWO_PASSWORD: str = "bob123"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def fixed_users(self) -> list[tuple[int, str, str]]:
        return [
            (1, self.USER_ONE_USERNAME, self.USER_ONE_PASSWORD),
            (2, self.USER_TWO_USERNAME, self.USER_TWO_PASSWORD),
        ]

    @property
    def fixed_usernames(self) -> set[str]:
        return {self.USER_ONE_USERNAME, self.USER_TWO_USERNAME}

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        self.ENVIRONMENT = self.ENVIRONMENT.lower()

        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")

        if self.USER_ONE_USERNAME.strip().lower() == self.USER_TWO_USERNAME.strip().lower():
            raise ValueError("The two fixed usernames must be different")

        if len(self.USER_ONE_PASSWORD) < 8 or len(self.USER_TWO_PASSWORD) < 8:
            raise ValueError("Fixed account passwords must be at least 8 characters long")

        if self.ENVIRONMENT == "production":
            self.FORCE_HTTPS = True

        return self


settings = Settings()
