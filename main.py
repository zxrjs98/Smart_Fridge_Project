import flet as ft
import requests

SERVER_URL = "http://127.0.0.1:8000"

def main(page: ft.Page):
    page.title = "스마트 냉장고 관리"
    page.window_width = 400
    page.window_height = 700
    page.theme_mode = ft.ThemeMode.LIGHT

    inventory_column = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

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

    # 리스트에서 아이템 삭제 (화면상 삭제)
    def remove_item_from_server(name, item_row):
        try:
            inventory_column.controls.remove(item_row)
            page.update()
            # Tip: 실제 DB 삭제 연동 시 여기에 requests.delete 추가
        except Exception as e:
            print(f"삭제 오류: {e}")

    # UI 아이템 생성 (IconButton 에러 방지 적용)
    def add_item_to_ui(name, date):
        new_row = ft.ListTile(
            leading=ft.Icon(ft.icons.KITCHEN, color=ft.colors.BLUE),
            title=ft.Text(name, weight="bold"),
            subtitle=ft.Text(f"소비기한: {date}"),
            trailing=ft.IconButton(
                icon=ft.icons.DELETE_OUTLINE, # 아이콘 명시 필수
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
    name_input = ft.TextField(label="재료 이름")
    date_input = ft.TextField(label="소비기한")
    add_dialog = ft.AlertDialog(
        title=ft.Text("새 재료 등록"),
        content=ft.Column([name_input, date_input], tight=True),
        actions=[ft.ElevatedButton("등록하기", on_click=save_item)],
    )

    def show_dialog(e):
        page.dialog = add_dialog
        add_dialog.open = True
        page.update()

    # 화면 구성
    page.add(
        ft.AppBar(title=ft.Text("우리집 냉장고"), bgcolor=ft.colors.BLUE_50, center_title=True),
        inventory_column,
        ft.FloatingActionButton(icon=ft.icons.ADD, on_click=show_dialog, bgcolor=ft.colors.BLUE)
    )

    fetch_items()

if __name__ == "__main__":
    ft.app(target=main)