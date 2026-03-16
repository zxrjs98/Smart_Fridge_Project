import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    BASE_URL: str = os.getenv("BASE_URL")
    # 나중에 추가될 API 키나 보안 설정도 여기서 관리합니다.

settings = Settings()