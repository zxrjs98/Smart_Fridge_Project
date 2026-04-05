Smart_Fridge_Project
냉장고 식재료 관리 및 레시피 추천 졸업 프로젝트

1. 개발 환경
Language: Python 3.x

Database: MySQL Server 8.0+

Management: MySQL Workbench, Git

2. 로컬 환경 세팅 (Initial Setup)

2.1 가상환경 및 패키지 설치
PowerShell
# 가상환경 생성 및 활성화
py -m venv .venv
* 안되면 python -m venv .venv

.\.venv\Scripts\activate

# 필수 패키지 설치
pip install -r requirements.txt
2.2 데이터베이스(DB) 구성
MySQL Workbench 접속

database/init_db.sql 파일 열기 및 전체 실행(Execute)

사용자 연동을 위한 컬럼 추가 (New Query):

SQL
USE refrigerator_db;
ALTER TABLE user_items ADD COLUMN user_id INT DEFAULT 1;
2.3 환경 변수 설정
프로젝트 루트 디렉토리에 .env 파일을 생성하고 아래 정보를 입력합니다.

Plaintext
DATABASE_URL=mysql+pymysql://[DB계정]:[비밀번호]@localhost:3306/refrigerator_db
NAVER_OCR_API_URL=[선택사항]
NAVER_OCR_SECRET_KEY=[선택사항]
3. 실행 방법 (Execution)
PowerShell
# 가상환경 활성화 상태에서 실행
python -m uvicorn server:app --reload
Web Access: http://127.0.0.1:8000

4. 소스 코드 관리
Repository: https://github.com/zxrjs98/Smart_Fridge_Project.git
