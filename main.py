import flet as ft
import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()
SERVER_URL = 'https://charlotte-calenturish-santana.ngrok-free.dev'

def main(page: ft.Page):
    page.title = "FreshKeep"
    page.window_width = 400
    page.window_height = 750
    page.theme_mode = ft.ThemeMode.LIGHT
    
    # 1. 목록이 들어갈 컬럼 (스크롤 가능하게 설정)
    inventory_column = ft.Column(expand=True, scroll=ft.ScrollMode.ALWAYS)

    # 2. 데이터 불러오기 함수
    def fetch_items(e=None):
        try:
            print("🔄 데이터 불러오는 중...")
            res = requests.get(f"{SERVER_URL}/items", timeout=5)
            if res.status_code == 200:
                items = res.json()
                inventory_column.controls.clear()
                
                for item in items:
                    # D-Day에 따른 색상 정하기
                    d_day = item.get('d_day')
                    t_color = "red" if d_day is not None and d_day <= 1 else "black"
                    d_text = "🚨 임박" if d_day is not None and d_day <= 1 else f"D-{d_day}"
                    
                    # 리스트에 추가
                    inventory_column.controls.append(
                        ft.Container(
                            content=ft.ListTile(
                                leading=ft.Icon(ft.Icons.KITCHEN, color="blue"),
                                title=ft.Text(item['name'], weight="bold", color=t_color),
                                subtitle=ft.Text(f"{item.get('expiry_date')} | {d_text}", color=t_color),
                                trailing=ft.IconButton(
                                    icon=ft.Icons.DELETE, 
                                    on_click=lambda _, n=item['name']: remove_item(n)
                                )
                            ),
                            border=ft.border.all(1, "black12"),
                            border_radius=10
                        )
                    )
                print(f"✅ {len(items)}개 목록 갱신 완료")
                page.update()
        except Exception as ex:
            print(f"❌ 오류: {ex}")

    def remove_item(name):
        requests.delete(f"{SERVER_URL}/items/{name}")
        fetch_items()

    # 3. 등록 팝업 관련
    name_input = ft.TextField(label="재료명")
    date_input = ft.TextField(label="기한 (YYYY-MM-DD)")

    def save_action(e):
        if name_input.value:
            payload = {"name": name_input.value, "expiry_date": date_input.value}
            requests.post(f"{SERVER_URL}/items", json=payload)
            add_dialog.open = False
            name_input.value = ""
            date_input.value = ""
            page.update()
            time.sleep(0.5)
            fetch_items()

    add_dialog = ft.AlertDialog(
        title=ft.Text("새 재료 등록"),
        content=ft.Column([name_input, date_input], tight=True),
        actions=[ft.TextButton("등록", on_click=save_action)]
    )
    page.overlay.append(add_dialog)

    # 4. 화면 구성 (여기가 핵심!)
    # 상단바 설정
    page.appbar = ft.AppBar(
        title=ft.Text("우리집 냉장고"),
        bgcolor="blue",
        actions=[ft.IconButton(icon=ft.Icons.REFRESH, on_click=fetch_items)]
    )

    # 메인 화면에 들어갈 요소들
    page.add(
        ft.Text("냉장고 현황", size=25, weight="bold"),
        ft.Divider(),
        # 컬럼을 Container로 감싸서 높이를 확보해줍니다.
        ft.Container(content=inventory_column, expand=True), 
        ft.FloatingActionButton(
            icon=ft.Icons.ADD, 
            on_click=lambda _: (setattr(add_dialog, "open", True), page.update()),
            bgcolor="blue"
        )
    )

    # 시작하자마자 데이터 불러오기
    fetch_items()

if __name__ == "__main__":
    ft.app(target=main)