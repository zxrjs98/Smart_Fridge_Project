import flet as ft
import requests
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from database.connection import engine, Base
from database import models
from datetime import datetime # 🟢 날짜 계산을 위해 추가

# 서버 시작 시 테이블 자동 생성 
Base.metadata.create_all(bind=engine)

app = FastAPI()

load_dotenv()
SERVER_URL = "https://charlotte-calenturish-santana.ngrok-free.dev"

def main(page: ft.Page):
    page.title = "스마트 냉장고 관리"
    page.window_width = 400
    page.window_height = 700
    page.theme_mode = ft.ThemeMode.LIGHT

    inventory_column = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

    # 🟢 유통기한 날짜 계산해서 색상 반환하는 함수 (추가됨)
    def get_expiry_color(date_str):
        try:
            today = datetime.now().date()
            # 입력된 날짜 형식이 'YYYY-MM-DD' 형태라고 가정
            expiry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            diff = (expiry_date - today).days

            if diff < 0:
                return ft.Colors.RED      # 유통기한 지남 (빨간색)
            elif diff <= 3:
                return ft.Colors.ORANGE   # 3일 이내 임박 (주황색)
            else:
                return ft.Colors.BLACK    # 넉넉함 (검정색)
        except ValueError:
            return ft.Colors.BLACK        # 날짜 형식을 다르게 적었을 경우

    # 서버에서 데이터 가져오기
    def fetch_items():
        try:
            response = requests.get(f"{SERVER_URL}/items")
            if response.status_code == 200:
                inventory_column.controls.clear()
                for item in response.json():
                    add_item_to_ui(item['name'], item['date'])
                page.update()
        except Exception as e:
            print(f"서버 연결 오류: {e}")

    # 리스트에서 아이템 삭제 (서버 연동 버전)
    def remove_item_from_server(name, item_row):
        try:
            # 1. 서버(DB)에 삭제 요청 보내기
            response = requests.delete(f"{SERVER_URL}/items/{name}")
            
            if response.status_code == 200:
                # 2. 서버 삭제 성공 시에만 화면에서 제거
                inventory_column.controls.remove(item_row)
                page.update()
                print(f"{name} 삭제 완료")
            else:
                print("서버 삭제 실패")
        except Exception as e:
            print(f"삭제 오류: {e}")

    # UI 아이템 생성 (🟢 색상 로직 적용)
    def add_item_to_ui(name, date):
        text_color = get_expiry_color(date) # 글자색 계산
        
        new_row = ft.ListTile(
            leading=ft.Icon(ft.Icons.KITCHEN, color=ft.Colors.BLUE),
            title=ft.Text(name, weight="bold"),
            subtitle=ft.Text(f"소비기한: {date}", color=text_color), # 계산된 색상 적용
            trailing=ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE, 
                on_click=lambda _: remove_item_from_server(name, new_row)
            )
        )
        inventory_column.controls.append(new_row)

    # 서버에 데이터 저장
    def save_item(e):
        if name_input.value:
            payload = {"name": name_input.value, "date": date_input.value}
            try:
                response = requests.post(f"{SERVER_URL}/items", json=payload)
                if response.status_code == 200:
                    fetch_items()
                    name_input.value = ""
                    date_input.value = ""
                    add_dialog.open = False
                    page.update()
            except Exception as e:
                print(f"저장 오류: {e}")

    # 입력 팝업 설정
    name_input = ft.TextField(label="재료 이름", hint_text="예: 우유")
    date_input = ft.TextField(label="소비기한", hint_text="예: 2026-04-10")
    add_dialog = ft.AlertDialog(
        title=ft.Text("새 재료 등록"),
        content=ft.Column([name_input, date_input], tight=True),
        actions=[ft.ElevatedButton("등록하기", on_click=save_item)],
    )

    def show_dialog(e):
        page.overlay.append(add_dialog) # 🟢 Flet 최신 버전 에러 방지용으로 수정
        add_dialog.open = True
        page.update()

    # 화면 구성
    page.add(
        ft.AppBar(
            title=ft.Text("우리집 냉장고"), 
            bgcolor=ft.Colors.BLUE_50, 
            center_title=True,
            actions=[
                ft.IconButton(
                    icon=ft.Icons.REFRESH, 
                    on_click=lambda _: fetch_items(),
                    tooltip="새로고침"
                )
            ]
        ),
        inventory_column,
        ft.FloatingActionButton(
            icon=ft.Icons.ADD, 
            on_click=show_dialog, 
            bgcolor=ft.Colors.BLUE
        )
    )

    fetch_items()

if __name__ == "__main__":
    ft.app(target=main)