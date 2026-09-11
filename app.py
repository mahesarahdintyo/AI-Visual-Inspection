import cv2
import numpy as np
import time
import serial

# ==========================================================
# 1. KONFIGURASI SERIAL ESP32 / WOKWI
# ==========================================================
IS_SIMULATION = True   # False jika menggunakan ESP32 Fisik
SERIAL_PORT = 'COM3'    # Port COM untuk ESP32 Fisik

try:
    if IS_SIMULATION:
        arduino = serial.serial_for_url('rfc2217://localhost:4000', baudrate=115200, timeout=1)
        print("[CONNECTED] Terhubung ke Wokwi Simulator (rfc2217://localhost:4000)")
    else:
        arduino = serial.Serial(SERIAL_PORT, 115200, timeout=1)
        print(f"[CONNECTED] Terhubung ke ESP32 Fisik ({SERIAL_PORT})")
except Exception as e:
    print(f"[WARN] Serial belum terhubung: {e}")
    arduino = None

def send_command(cmd):
    if arduino and arduino.is_open:
        try:
            arduino.write(f"{cmd}\n".encode('utf-8'))
        except Exception as e:
            print(f"[ERR] Gagal kirim serial: {e}")

# ==========================================================
# 2. KONFIGURASI KAMERA & TAMPILAN SISTEM (ENTERPRISE AOI)
# ==========================================================
APP_TITLE = "AOI-Vision Pro // Industrial Quality Inspection System"
WINDOW_NAME = "AOI-Vision Pro - Automated Optical Inspection"
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WINDOW_NAME, 1080, 720)

cam_index = 1  # 1 untuk Camo/kamera eksternal, 0 untuk webcam laptop
cap = cv2.VideoCapture(cam_index)

if not cap.isOpened():
    print(f"[WARN] Kamera index {cam_index} tidak terbuka, beralih ke index 0...")
    cam_index = 0
    cap = cv2.VideoCapture(cam_index)

# Variabel Animasi Scanning & Kontrol
scan_y_offset = 0
scan_direction = 1
scan_speed = 6
last_state = ""
last_send_time = 0
fps_time = time.time()
fps = 30.0

# Debouncing buffer kestabilan status (mencegah flickering)
state_history = []
HISTORY_LEN = 4

# ==========================================================
# 3. ELEMEN GRAFIS HUD KELAS INDUSTRI
# ==========================================================
def draw_precision_brackets(img, x, y, w, h, color, length=28, thickness=2):
    """Menggambar bracket sudut presisi industri"""
    # Kiri-Atas
    cv2.line(img, (x, y), (x + length, y), color, thickness)
    cv2.line(img, (x, y), (x, y + length), color, thickness)
    # Kanan-Atas
    cv2.line(img, (x + w, y), (x + w - length, y), color, thickness)
    cv2.line(img, (x + w, y), (x + w, y + length), color, thickness)
    # Kiri-Bawah
    cv2.line(img, (x, y + h), (x + length, y + h), color, thickness)
    cv2.line(img, (x, y + h), (x, y + h - length), color, thickness)
    # Kanan-Bawah
    cv2.line(img, (x + w, y + h), (x + w - length, y + h), color, thickness)
    cv2.line(img, (x + w, y + h), (x + w, y + h - length), color, thickness)

def draw_hud_header(img, w, is_locked, fps_val, cam_id):
    """Dashboard status bar profesional di bagian atas"""
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, 52), (18, 22, 28), -1)
    cv2.line(overlay, (0, 52), (w, 52), (0, 180, 240), 1)
    cv2.addWeighted(overlay, 0.85, img, 0.15, 0, img)

    # Nama Software Industri
    cv2.putText(img, "AOI-VISION PRO // AUTOMATED QUALITY CONTROL", (25, 33),
                cv2.FONT_HERSHEY_DUPLEX, 0.65, (0, 220, 255), 2)

    # Status Lock Target
    status_text = "TARGET: ACQUIRED" if is_locked else "TARGET: SCANNING"
    status_color = (0, 255, 120) if is_locked else (0, 190, 255)
    cv2.putText(img, status_text, (w - 410, 33),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, status_color, 1)

    # Telemetri FPS & Port Kamera
    fps_text = f"FPS: {fps_val:.1f} | CAM: [{cam_id}]"
    cv2.putText(img, fps_text, (w - 190, 33),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (190, 190, 190), 1)

# ==========================================================
# 4. MAIN LOOP INSPEKSI
# ==========================================================
print(f"[INFO] {APP_TITLE} Aktif!")
print("[INFO] Tekan 'q' untuk keluar | Tekan 'c' untuk beralih kamera (0 / 1)")

while True:
    ret, frame = cap.read()
    if not ret:
        time.sleep(0.05)
        continue

    # Hitung FPS
    now = time.time()
    dt = now - fps_time
    fps_time = now
    if dt > 0:
        fps = (fps * 0.9) + ((1.0 / dt) * 0.1)

    frame = cv2.flip(frame, 1)
    display_frame = frame.copy()
    h, w, _ = frame.shape

    # ------------------------------------------------------
    # A. SEGMENTASI PRESISI: ISOLASI KERTAS PUTIH vs MEJA KAYU
    # ------------------------------------------------------
    # Kertas putih: Saturation SANGAT RENDAH (mendekati 0) & Value TINGGI
    # Meja kayu/refleksi: Saturation TINGGI (> 55) & Value lebih gelap
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # 1. Filter HSV ketat: Batasi saturation maksimal 38 agar meja kayu tereliminasi 100%
    lower_white = np.array([0, 0, 140])
    upper_white = np.array([180, 38, 255])
    mask_hsv = cv2.inRange(hsv, lower_white, upper_white)

    # 2. Filter Kecerahan Grayscale
    _, mask_gray = cv2.threshold(gray, 145, 255, cv2.THRESH_BINARY)

    # Kombinasikan kedua filter (Intersection)
    thresh = cv2.bitwise_and(mask_hsv, mask_gray)

    # Bersihkan noise dengan kernel kecil agar tidak menyambung ke refleksi meja
    kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_small, iterations=1)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_small, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter kontur benda kerja yang valid berdasarkan luas minimum
    valid_contours = [c for c in contours if cv2.contourArea(c) > 6000]

    is_target_found = len(valid_contours) > 0

    if is_target_found:
        # Ambil kontur benda kerja terbesar (kertas putih yang diinspeksi)
        main_obj = max(valid_contours, key=cv2.contourArea)
        x, y, bw, bh = cv2.boundingRect(main_obj)

        # --------------------------------------------------
        # B. DETEKSI CACAT / SOBEKAN / DEFECT (INTERNAL ROI)
        # --------------------------------------------------
        # Margin 12px ke dalam agar perbatasan tepi luar kertas tidak dianggap cacat
        margin = 12
        defects = []

        if bw > (2 * margin + 15) and bh > (2 * margin + 15):
            roi_inner = frame[y + margin : y + bh - margin, x + margin : x + bw - margin]
            roi_gray = cv2.cvtColor(roi_inner, cv2.COLOR_BGR2GRAY)
            roi_blur = cv2.GaussianBlur(roi_gray, (5, 5), 0)

            # Canny edge detector khusus mendeteksi robekan atau goresan di dalam benda kerja
            edges = cv2.Canny(roi_blur, 50, 140)
            defect_contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

            for dc in defect_contours:
                arc_len = cv2.arcLength(dc, False)
                _, _, dw, dh = cv2.boundingRect(dc)
                diag = np.sqrt(dw**2 + dh**2)

                # Syarat cacat: panjang garis > 35px atau ukuran diagonal > 22px
                # dan tidak melebihi ukuran kertas (menghindari false trigger)
                if (arc_len > 35 or diag > 22) and (dw < bw * 0.85 and dh < bh * 0.85):
                    defects.append((dc, margin))

        # Stabilkan status inspeksi (debouncing history buffer)
        raw_status = "NG" if len(defects) > 0 else "OK"
        state_history.append(raw_status)
        if len(state_history) > HISTORY_LEN:
            state_history.pop(0)

        # Status keputusan final berdasarkan frame terbaru
        is_defect = state_history.count("NG") >= (HISTORY_LEN // 2 + 1)
        current_cmd = "NG" if is_defect else "OK"

        # Kirim sinyal serial ke ESP32 / Wokwi jika status berubah
        if current_cmd != last_state or (time.time() - last_send_time > 1.5):
            send_command(current_cmd)
            last_state = current_cmd
            last_send_time = time.time()

        # --------------------------------------------------
        # C. ANIMASI SCANNING LASER (Optical Sweeper)
        # --------------------------------------------------
        scan_y_offset += scan_speed * scan_direction
        if scan_y_offset >= bh:
            scan_y_offset = bh
            scan_direction = -1
        elif scan_y_offset <= 0:
            scan_y_offset = 0
            scan_direction = 1

        scan_line_y = int(np.clip(y + scan_y_offset, 0, h - 1))

        # Efek Laser Sweep Glow
        glow_overlay = display_frame.copy()
        glow_height = 16
        gy1 = max(y, scan_line_y - glow_height if scan_direction > 0 else scan_line_y)
        gy2 = min(y + bh, scan_line_y if scan_direction > 0 else scan_line_y + glow_height)
        
        laser_color = (0, 120, 255) if is_defect else (0, 230, 255)
        cv2.rectangle(glow_overlay, (x, gy1), (x + bw, gy2), laser_color, -1)
        cv2.addWeighted(glow_overlay, 0.20, display_frame, 0.80, 0, display_frame)

        # Garis inti laser
        cv2.line(display_frame, (x, scan_line_y), (x + bw, scan_line_y), (255, 255, 255), 2)

        # --------------------------------------------------
        # D. HUD BRACKET PRESISI & BADGE STATUS
        # --------------------------------------------------
        hud_color = (0, 30, 255) if is_defect else (0, 255, 90)
        draw_precision_brackets(display_frame, x, y, bw, bh, hud_color, length=32, thickness=3)

        # Garis batas tipis mengikuti dimensi pas kertas
        cv2.rectangle(display_frame, (x, y), (x + bw, y + bh), hud_color, 1)

        # Telemetri dimensi fisik objek di bawah kotak
        telemetry_str = f"DIM: {bw}x{bh}px | LOC: [{x},{y}]"
        cv2.putText(display_frame, telemetry_str, (x, y + bh + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)

        # Lebar badge dinamis menyesuaikan lebar objek
        badge_w = max(280, min(bw, 360))

        if is_defect:
            # STATUS NG / REJECT
            badge_text = f"[ DEFECT DETECTED | REJECT ({len(defects)}) ]"
            cv2.rectangle(display_frame, (x, y - 36), (x + badge_w, y - 8), (0, 0, 180), -1)
            cv2.putText(display_frame, badge_text, (x + 8, y - 16),
                        cv2.FONT_HERSHEY_DUPLEX, 0.58, (255, 255, 255), 1)
            cv2.line(display_frame, (x, y - 8), (x + badge_w, y - 8), (0, 30, 255), 2)

            # ----------------------------------------------
            # E. TARGET RETICLE TEPAT DI TITIK CACAT
            # ----------------------------------------------
            for idx, (dc, offset_m) in enumerate(defects[:4]):
                dx, dy, dw, dh = cv2.boundingRect(dc)
                center_x = x + offset_m + dx + dw // 2
                center_y = y + offset_m + dy + dh // 2
                radius = max(14, int(max(dw, dh) / 1.4))

                # Reticle Merah
                cv2.circle(display_frame, (center_x, center_y), radius, (0, 30, 255), 2)
                cv2.circle(display_frame, (center_x, center_y), 3, (0, 255, 255), -1)

                # Crosshair Reticle
                ch_len = 5
                cv2.line(display_frame, (center_x - radius - ch_len, center_y), (center_x - radius, center_y), (0, 30, 255), 2)
                cv2.line(display_frame, (center_x + radius, center_y), (center_x + radius + ch_len, center_y), (0, 30, 255), 2)
                cv2.line(display_frame, (center_x, center_y - radius - ch_len), (center_x, center_y - radius), (0, 30, 255), 2)
                cv2.line(display_frame, (center_x, center_y + radius), (center_x, center_y + radius + ch_len), (0, 30, 255), 2)

                # Garis Pointer / Leader Tag
                tag_x = center_x + radius + 15
                tag_y = center_y - 12
                cv2.line(display_frame, (center_x + radius, center_y), (tag_x, tag_y), (0, 255, 255), 1)
                cv2.line(display_frame, (tag_x, tag_y), (tag_x + 55, tag_y), (0, 255, 255), 1)
                cv2.putText(display_frame, f"ERR #{idx+1}", (tag_x + 4, tag_y - 3),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)

        else:
            # STATUS OK / PASS
            badge_text = "[ QUALITY OK | SPEC APPROVED ]"
            cv2.rectangle(display_frame, (x, y - 36), (x + badge_w, y - 8), (0, 135, 45), -1)
            cv2.putText(display_frame, badge_text, (x + 8, y - 16),
                        cv2.FONT_HERSHEY_DUPLEX, 0.58, (255, 255, 255), 1)
            cv2.line(display_frame, (x, y - 8), (x + badge_w, y - 8), (0, 255, 100), 2)

    else:
        # --------------------------------------------------
        # F. TAMPILAN STANDBY / SEARCHING WORKPIECE
        # --------------------------------------------------
        state_history.clear()
        
        # Crosshair tengah
        cx, cy = w // 2, h // 2
        radar_color = (0, 180, 240)
        cv2.circle(display_frame, (cx, cy), 50, radar_color, 1)
        cv2.circle(display_frame, (cx, cy), 110, radar_color, 1)
        cv2.line(display_frame, (cx - 130, cy), (cx + 130, cy), radar_color, 1)
        cv2.line(display_frame, (cx, cy - 130), (cx, cy + 130), radar_color, 1)

        # Pesan Standby Profesional
        standby_text = "AOI SYSTEM STANDBY // SCANNING FOR WORKPIECE..."
        cv2.putText(display_frame, standby_text, (cx - 260, cy + 150),
                    cv2.FONT_HERSHEY_DUPLEX, 0.60, (240, 240, 240), 1)

    # Header Dashboard
    draw_hud_header(display_frame, w, is_target_found, fps, cam_index)

    # Tampilkan jendela inspeksi
    cv2.imshow(WINDOW_NAME, display_frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('c'):
        # Toggle kamera
        cam_index = 0 if cam_index == 1 else 1
        print(f"[INFO] Beralih ke Kamera Index: {cam_index}")
        cap.release()
        cap = cv2.VideoCapture(cam_index)

# Selesai
if arduino and arduino.is_open:
    arduino.close()
cap.release()
cv2.destroyAllWindows()