import cv2
import numpy as np
import serial
import time
import keras # type: ignore

# --- 1. LOAD MODEL AI ---
print("[INFO] Memuat Model AI...")
model_layer = keras.layers.TFSMLayer("model.savedmodel", call_endpoint="serving_default")
class_names = [line.strip() for line in open("labels.txt", "r").readlines()]
print("[INFO] Model AI Berhasil Dimuat!")

# --- 2. KONFIGURASI SERIAL ESP32 ---
IS_SIMULATION = True

try:
    if IS_SIMULATION:
        arduino = serial.serial_for_url('rfc2217://localhost:4000', baudrate=115200, timeout=1)
        print("[CONNECTED] Terhubung ke Wokwi Simulator")
    else:
        arduino = serial.Serial('COM3', 115200, timeout=1)
        print("[CONNECTED] Terhubung ke ESP32 Fisik")
    time.sleep(2)
except Exception as e:
    print(f"[ERROR] Koneksi Serial Gagal: {e}")
    arduino = None

def send_command(cmd):
    if arduino and arduino.is_open:
        arduino.write(f"{cmd}\n".encode('utf-8'))

# --- 3. KONFIGURASI KAMERA (FIXED FOR CAMO) ---
WINDOW_NAME = "AI Visual Inspection - Camo Camera Fixed"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, 960, 540)

# Gunakan indeks Camo (biasanya 1/2). Lepas backend CAP_DSHOW agar Camo tidak black screen!
CAM_INDEX = 1  # Ubah ke 2 jika indeks 1 masih hitam
cap = cv2.VideoCapture(CAM_INDEX)

last_state = ""
last_send_time = 0

# OPTIMASI: AI dijalankan setiap 6 frame sekali agar FPS sangat mulus
frame_count = 0
AI_PREDICT_INTERVAL = 6  
current_status = "INITIALIZING..."
color_status = (255, 192, 0)

while True:
    ret, frame = cap.read()
    if not ret:
        print("[WARN] Gagal membaca frame dari Camo. Membaca ulang...")
        time.sleep(0.1)
        continue

    frame = cv2.flip(frame, 1)
    height, width, _ = frame.shape
    frame_count += 1

    # Area Inspeksi (ROI)
    box_size = 300
    x1, y1 = int((width - box_size) / 2), int((height - box_size) / 2)
    x2, y2 = x1 + box_size, y1 + box_size
    
    roi = frame[y1:y2, x1:x2]

    # --- A. PROSES CONTOUR OPENCV (Deteksi Garis Cacat) ---
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # --- B. INFERENSI AI (Ringan & Ringkas) ---
    if frame_count % AI_PREDICT_INTERVAL == 0:
        image_resized = cv2.resize(roi, (224, 224), interpolation=cv2.INTER_AREA)
        image_array = np.asarray(image_resized, dtype=np.float32).reshape(1, 224, 224, 3)
        normalized_image_array = (image_array / 127.5) - 1.0

        outputs = model_layer(normalized_image_array)
        prediction_tensor = list(outputs.values())[0]
        prediction = prediction_tensor.numpy()

        index = np.argmax(prediction)
        class_name = class_names[index]
        confidence_score = prediction[0][index]
        label_detected = class_name.split(' ', 1)[-1].strip().upper()

        if label_detected == "OK" and confidence_score > 0.7:
            current_status = f"PART OK ({confidence_score*100:.1f}%)"
            color_status = (0, 255, 0)
            cmd_to_send = "OK"
        else:
            current_status = f"PART NG / DEFECT ({confidence_score*100:.1f}%)"
            color_status = (0, 0, 255)
            cmd_to_send = "NG"

        if cmd_to_send != last_state or (time.time() - last_send_time > 1.0):
            send_command(cmd_to_send)
            last_state = cmd_to_send
            last_send_time = time.time()

    # --- C. GAMBAR GARIS SENSOR KONTUR ---
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 20 < area < 4000:
            cv2.drawContours(roi, [cnt], -1, color_status, 2)

    # --- D. OVERLAY MONITOR ---
    cv2.rectangle(frame, (x1, y1), (x2, y2), color_status, 3)
    
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (width, 70), (30, 30, 30), -1)
    frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)

    cv2.putText(frame, f"STATUS: {current_status}", (20, 45),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_status, 2)

    cv2.imshow(WINDOW_NAME, frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

if arduino and arduino.is_open:
    arduino.close()
cap.release()
cv2.destroyAllWindows()