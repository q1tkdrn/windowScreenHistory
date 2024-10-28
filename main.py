from PIL import Image, ImageChops, ImageOps, ImageTk, ImageDraw
from screeninfo import get_monitors
import time
import os
import tkinter as tk
from tkinter import Label, Scale, HORIZONTAL, OptionMenu, StringVar
import threading
import mss
import keyboard
import pystray  # 시스템 트레이 아이콘을 위한 pystray 라이브러리
import winreg
import configparser
import shutil
import sys

# 폴더를 만들어 이미지 파일을 저장할 준비
output_folder = "screen_captures/" + str(int(time.time()))
os.makedirs(output_folder, exist_ok=True)
config_path = "config.ini"
config = configparser.ConfigParser()
global stop
stop = False

def configSetting():
    config["DEFAULT"]["maxStorage"] = "0"
    config["DEFAULT"]["capture_time"] = "5"
    config["DEFAULT"]["keybind"] = "win+ctrl+shift+d"
    with open(config_path, "w") as config_file:
            config.write(config_file)
if os.path.exists(config_path):
    config.read(config_path)
    for i in ["maxStorage","capture_time","keybind"]:
        if not i in config["DEFAULT"]:
            configSetting()
            break
    if config["DEFAULT"]["maxStorage"] + config["DEFAULT"]["capture_time"] != str(int(config["DEFAULT"]["maxStorage"])) + str(int(config["DEFAULT"]["capture_time"])):
        configSetting()
else:
    configSetting()
maxStorage = float(config["DEFAULT"]["maxStorage"])
capture_time = int(config["DEFAULT"]["capture_time"])
keybind = config["DEFAULT"]["keybind"]

# 폴더 크기 확인
def get_dir_size(path='.'):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    return float(total)/1024

# 오래된 폴더 삭제
def delete_oldest_folder(folder_path):
    # 삭제할 폴더 정보 저장
    oldest_folder = None
    oldest_time = float('inf')

    # 해당 폴더 내의 모든 하위 폴더 탐색
    for root, dirs, files in os.walk(folder_path):
        for dir in dirs:
            dir_path = os.path.join(root, dir)
            # 폴더 생성 시간 가져오기
            mtime = os.path.getmtime(dir_path)
            # 가장 오래된 폴더 정보 업데이트
            if mtime < oldest_time:
                oldest_time = mtime
                oldest_folder = dir_path

    # 가장 오래된 폴더 삭제
    if oldest_folder and oldest_folder[-10:] != output_folder[-10:]:
        shutil.rmtree(oldest_folder)

# 여러 모니터의 해상도 가져오기
monitors = get_monitors()
display_window = None  # GUI 창 객체를 전역 변수로 정의
capturing = True  # 캡처 상태를 제어하는 전역 변수
app_name = "window screen history"
app_exe_path = sys.argv[0]

# 프로그램을 종료하는 함수
def quit_program(icon, item):
    icon.stop()
    root.quit()
    root.destroy()
    global stop
    stop = True

# 캡처한 이미지 파일을 저장하는 함수
def save_capture(image, index, monitor_index):
    filename = os.path.join(output_folder, f"capture_monitor{monitor_index}_{index}.png")
    image.save(filename, "jpeg", quality = 75)
    if get_dir_size("screen_captures") >= maxStorage and maxStorage != 0.0:
        delete_oldest_folder("screen_captures")
    return filename

# 화면 변화를 감지하는 함수
def has_changed(image1, image2):
    diff = ImageChops.difference(image1, image2).getbbox()
    return diff is not None

# 캡처를 시작하는 함수 (mss 사용)
def start_capture(interval=1, captured_files=None):
    last_images = [None] * len(monitors)
    index = 0

    with mss.mss() as sct:
        while True:
            if not capturing:  # 캡처 중지 상태면 대기
                time.sleep(0.5)
                continue
            global stop
            if stop:
                break
            
            for monitor_index, monitor in enumerate(monitors):
                monitor_bbox = {
                    "top": monitor.y,
                    "left": monitor.x,
                    "width": monitor.width,
                    "height": monitor.height
                }
                current_image = sct.grab(monitor_bbox)
                current_image = Image.frombytes("RGB", current_image.size, current_image.bgra, "raw", "BGRX")
                
                if last_images[monitor_index] is None or has_changed(last_images[monitor_index], current_image):
                    filename = save_capture(current_image, index, monitor_index)
                    captured_files[monitor_index].append(filename)
                    last_images[monitor_index] = current_image
                    index += 1
            time.sleep(interval)

# GUI를 사용하여 이미지 탐색
def display_captures(captured_files):
    global display_window, capturing

    if display_window is not None:
        display_window.destroy()  # 이미 창이 열려 있으면 닫음
        display_window = None
        capturing = True  # 창이 닫히면 캡처 재개
        return

    capturing = False  # 창이 열리면 캡처 중지

    # 창을 새로 열기
    display_window = tk.Toplevel(root)
    display_window.title("윈도우 히스토리")

    # 창을 전체화면으로 설정
    display_window.attributes("-fullscreen", True)
    
    # 현재 선택된 모니터 인덱스
    selected_monitor = StringVar(display_window)
    selected_monitor.set("0")  # 기본값: 첫 번째 모니터
    image_index = [0]

    # 이미지 레이블 생성 및 배치 (배경에 배치)
    label = Label(display_window)
    label.place(relwidth=1, relheight=1)

    # 모니터 전환 옵션 메뉴 추가 (이미지 위에 겹치도록 배치)
    monitor_options = [str(i) for i in range(len(monitors))]
    monitor_menu = OptionMenu(display_window, selected_monitor, *monitor_options, command=lambda _: on_monitor_change())
    monitor_menu.place(relx=0.02, rely=0.02)

    # 슬라이더를 추가하여 이미지 탐색 가능하도록 설정 (이미지 위에 겹치도록 배치)
    slider = Scale(display_window, from_=0, to=0, orient=HORIZONTAL, length=300, command=lambda val: update_image(int(val)))
    slider.place(relx=0.5, rely=0.05, anchor="n")

    def update_image(index):
        # 현재 선택된 모니터의 이미지 업데이트
        monitor_index = int(selected_monitor.get())
        if 0 <= index < len(captured_files[monitor_index]):
            img = Image.open(captured_files[monitor_index][index])
            img = resize_to_window(img, display_window.winfo_width(), display_window.winfo_height())
            img = ImageTk.PhotoImage(img)
            label.config(image=img)
            label.image = img

    def resize_to_window(img, window_width, window_height):
        # 이미지 비율을 윈도우에 맞춰 리사이즈
        img_aspect_ratio = img.width / img.height
        window_aspect_ratio = window_width / window_height

        if img_aspect_ratio > window_aspect_ratio:  # 이미지가 창보다 더 넓음
            img = img.resize((window_width, int(window_width / img_aspect_ratio)), Image.LANCZOS)
        else:  # 이미지가 창보다 더 좁거나 같음
            img = img.resize((int(window_height * img_aspect_ratio), window_height), Image.LANCZOS)

        return img

    # 창 크기가 변경될 때 이미지 업데이트
    def on_resize(event):
        update_image(slider.get())

    display_window.bind("<Configure>", on_resize)

    # 모니터 선택 시 슬라이더 최댓값을 업데이트하고 현재 위치 설정
    def on_monitor_change():
        monitor_index = int(selected_monitor.get())
        slider.config(to=len(captured_files[monitor_index]) - 1)
        slider.set(len(captured_files[monitor_index]) - 1)
        update_image(slider.get())

    # 슬라이더의 최대값을 현재 모니터의 이미지 수에 따라 업데이트
    def update_slider():
        monitor_index = int(selected_monitor.get())
        current_max = len(captured_files[monitor_index]) - 1
        if slider.get() == slider["to"]:  # 슬라이더가 최댓값에 있는 경우에만 갱신
            slider.config(to=current_max)
            slider.set(current_max)
        else:  # 그렇지 않다면 현재 슬라이더 위치 유지
            slider.config(to=current_max)

    # 파일이 추가될 때마다 슬라이더 업데이트
    def monitor_captured_files():
        while display_window is not None:
            if len(captured_files[int(selected_monitor.get())]) > slider["to"]:
                display_window.after(100, update_slider)
            time.sleep(1)

    # 초기 이미지 업데이트
    update_image(slider.get())

    # 새 스레드에서 캡처된 파일 모니터링 시작
    threading.Thread(target=monitor_captured_files, daemon=True).start()

# 윈도우 시작 시 실행 설정을 확인하는 함수
def is_startup_enabled():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
        try:
            winreg.QueryValueEx(key, app_name)
            return True
        except FileNotFoundError:
            return False

# 윈도우 시작 시 실행 설정을 토글하는 함수
def toggle_startup():
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
        if is_startup_enabled():
            winreg.DeleteValue(key, app_name)
        else:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_exe_path)

# 시스템 트레이 아이콘 생성
def setup_tray_icon():
    icon_image = Image.new("RGB", (64, 64), (0, 0, 0))
    draw = ImageDraw.Draw(icon_image)
    draw.rectangle((16, 16, 48, 48), fill="white")  # 간단한 사각형 아이콘

    icon = pystray.Icon("screen_capture")
    icon.icon = icon_image
    icon.title = app_name
    icon.menu = pystray.Menu(
        pystray.MenuItem(
            "Start on Window Start", toggle_startup, checked=lambda item: is_startup_enabled()
        ),
        pystray.MenuItem("Exit", lambda: quit_program(icon, None))
    )
    icon.run()

# 메인 루트 창 생성
root = tk.Tk()
root.withdraw()  # 루트 창 숨기기 (UI만 표시하고 메인 창은 보이지 않게)

# 캡처된 이미지 파일 목록 준비
captured_files = [[] for _ in range(len(monitors))]  # 각 모니터별 파일 리스트
capture_thread = threading.Thread(target=start_capture, args=(capture_time, captured_files))
capture_thread.daemon = True
capture_thread.start()

# 단축키 설정 (Ctrl + Shift + D로 창 열기/닫기)
keyboard.add_hotkey(keybind, lambda: display_captures(captured_files))

# 시스템 트레이 아이콘 설정
tray_thread = threading.Thread(target=setup_tray_icon)
tray_thread.daemon = True
tray_thread.start()

# 프로그램 실행 상태 유지
root.mainloop()