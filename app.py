import cv2
import serial
import time

# --- KONFIGURASI KONEKSI ESP32 ---
IS_SIMULATION = True  # Ubah ke False jika nanti sudah memakai ESP32 Fisik (Kabel USB)

try:
    if IS_SIMULATION:
        # Koneksi ke Wokwi Simulator via RFC2217 Port 4000
        arduino = serial.serial_for_url('rfc2217://localhost:4000', baudrate=115200, timeout=1)
        print("[CONNECTED] Terhubung ke Wokwi Simulator Port 4000")
    else:
        # Koneksi ke ESP32 Fisik (Sesuaikan 'COM3' dengan port USB laptop kamu)
        arduino = serial.Serial('COM3', 115200, timeout=1)
        print("[CONNECTED] Terhubung ke ESP32 Fisik")
    time.sleep(2)
except Exception as e:
    print(f"[ERROR] Gagal terhubung ke ESP32/Wokwi: {e}")
    arduino = None

# --- KONFIGURASI KAMERA & DISPLAY ---
WINDOW_NAME = "AI Visual Inspection System - QC Monitor"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, 960, 540)

# Akses Kamera (0 = Webcam/Camo, ubah 1/2 jika menggunakan Camo iPhone)
cap = cv2.VideoCapture(1)

current_status = "READY"
color_status = (255, 192, 0) # Cyan

def send_command(cmd):
    """Fungsi untuk mengirim data ke ESP32"""
    if arduino and arduino.is_open:
        data = f"{cmd}\n"
        arduino.write(data.encode('utf-8'))
        print(f"--> Sinyal Dikirim ke ESP32: {cmd}")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Gagal mengakses kamera.")
        break

    frame = cv2.flip(frame, 1)
    height, width, _ = frame.shape

    # --- AREA INSPEKSI PART ---
    box_size = 250
    x1 = int((width - box_size) / 2)
    y1 = int((height - box_size) / 2)
    x2, y2 = x1 + box_size, y1 + box_size

    cv2.rectangle(frame, (x1, y1), (x2, y2), color_status, 3)
    cv2.putText(frame, "AREA INSPEKSI PART", (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_status, 2)

    # --- HEADER MONITOR ---
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (width, 80), (30, 30, 30), -1)
    frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)

    cv2.putText(frame, f"STATUS: {current_status}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, color_status, 3)
    cv2.putText(frame, "Simulasi Keyboard: [O] = OK | [N] = NG (Defect) | [Q] = Quit", 
                (20, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    cv2.imshow(WINDOW_NAME, frame)

    key = cv2.waitKey(1) & 0xFF

    if key in (ord('o'), ord('O')):
        current_status = "PART OK"
        color_status = (0, 255, 0) # Hijau
        send_command("OK")

    elif key in (ord('n'), ord('N')):
        current_status = "PART NG (DEFECT)"
        color_status = (0, 0, 255) # Merah
        send_command("NG")

    elif key in (ord('q'), ord('Q')):
        break

if arduino and arduino.is_open:
    arduino.close()
cap.release()
cv2.destroyAllWindows()