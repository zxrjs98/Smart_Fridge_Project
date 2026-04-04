from flask import Flask, request, jsonify, render_template
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# DB 연결 설정
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': os.getenv("DB_PASSWORD"),
    'db': os.getenv("DB_NAME"),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor # 데이터를 딕셔너리 형태로 가져옴
}

# 메인 페이지 로드
@app.route('/')
def index():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 내 냉장고 재료 불러오기
            cursor.execute("SELECT *, DATEDIFF(expiry_date, CURDATE()) as d_day FROM user_items ORDER BY expiry_date")
            items = cursor.fetchall()
        return render_template('index.html', items=items)
    finally:
        conn.close()

# 재료 검색
@app.route('/items/search')
def search_ingredients():
    query = request.args.get('q', '')
    conn = pymysql.connect(**DB_CONFIG)
    
    try:
        with conn.cursor() as cursor:
            if query == 'popular':
                sql = "SELECT name, is_seasoning FROM master_ingredients LIMIT 20"
                cursor.execute(sql)
            else:
                sql = "SELECT name, is_seasoning FROM master_ingredients WHERE name LIKE %s"
                cursor.execute(sql, ('%' + query + '%',))
            
            results = cursor.fetchall()
            return jsonify(results)
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)