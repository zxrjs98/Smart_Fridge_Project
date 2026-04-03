from flask import Flask, request, jsonify, render_template
import pymysql
import os
import time
import requests
import uuid
import base64
from datetime import datetime, timedelta
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
    'cursorclass': pymysql.cursors.DictCursor
}

# 1. 메인 화면 불러오기
@app.route('/')
def index():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT *, DATEDIFF(expiry_date, CURDATE()) as d_day FROM user_items ORDER BY expiry_date")
            items = cursor.fetchall()
        return render_template('index.html', items=items)
    finally:
        conn.close()

# 2. 재료 검색
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

# 3. 내 냉장고에 재료 추가
@app.route('/items', methods=['POST'])
def add_item():
    data = request.json
    name = data.get('name')
    exp = data.get('expiry_date')
    if not exp: exp = None
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO user_items (name, expiry_date) VALUES (%s, %s)", (name, exp))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# 4. 내 냉장고에서 재료 삭제
@app.route('/items/<name>', methods=['DELETE'])
def delete_item(name):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM user_items WHERE name = %s", (name,))
        conn.commit()
        return jsonify({"status": "success"})
    finally:
        conn.close()

# 5. 소비기한 수정
@app.route('/update-item/<name>', methods=['POST'])
def update_date(name):
    data = request.json
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE user_items SET expiry_date = %s WHERE name = %s", (data['expiry_date'], name))
        conn.commit()
        return jsonify({"status": "success"})
    finally:
        conn.close()

# 6. 레시피 탭 에러 방지용 (임시 빈 목록)
@app.route('/api/recipes')
def api_recipes():
    return jsonify([])

# 7. 영수증 스캔 (네이버 연동 + 임시 테스트 자동 전환 하이브리드 버전!)
@app.route('/scan_receipt', methods=['POST'])
def scan_receipt():
    if 'receipt' not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    file = request.files['receipt']
    
    invoke_url = os.getenv("OCR_URL")
    secret_key = os.getenv("OCR_SECRET_KEY")

    if not invoke_url or not secret_key:
        print("⚠️ 네이버 OCR 키가 없습니다! 가짜 데이터로 UI 테스트를 진행합니다.")
        import time
        time.sleep(2)
        
        mock_data = [
            {"name": "삼겹살", "expiry_date": "2026-04-10"},
            {"name": "대파", "expiry_date": "2026-04-10"},
            {"name": "깐마늘", "expiry_date": "2026-04-17"}
        ]
        return jsonify({"status": "success", "items": mock_data})

    try:
        image_bytes = file.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        request_json = {
            'images': [{'format': 'png', 'name': 'receipt_scan', 'data': image_base64}],
            'requestId': str(uuid.uuid4()),
            'version': 'V2',
            'timestamp': int(round(time.time() * 1000))
        }

        headers = {
            'X-OCR-SECRET': secret_key,
            'Content-Type': 'application/json'
        }

        response = requests.post(invoke_url, headers=headers, json=request_json)
        result = response.json()
        
        parsed_items = []
        if 'images' in result and result['images']:
            receipt_result = result['images'][0].get('receipt', {}).get('result', {})
            sub_results = receipt_result.get('subResults', [])
            
            if sub_results:
                items = sub_results[0].get('items', [])
                default_expiry = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
                
                for item in items:
                    name_text = item.get('name', {}).get('text', '')
                    if name_text:
                        parsed_items.append({
                            "name": name_text.replace(" ", ""),
                            "expiry_date": default_expiry
                        })

        if not parsed_items:
            return jsonify({"error": "영수증에서 글자를 읽지 못했어. 사진을 다시 찍어볼래?"}), 400

        return jsonify({"status": "success", "items": parsed_items})

    except Exception as e:
        print(f"OCR 에러 발생: {e}")
        return jsonify({"error": "네이버 서버와 통신 중 문제가 발생했어!"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)