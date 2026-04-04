import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True) # override 추가로 값 강제 갱신

class Settings:
    # .strip()을 추가해 공백이나 줄바꿈 문자를 제거
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    API_KEY = os.getenv("API_KEY", "").strip()

settings = Settings()