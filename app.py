import cv2
import mediapipe as mp
import numpy as np
import time
import tkinter as tk
from threading import Thread
from datetime import date
from tkinter import messagebox
import json
import os
import sys
from win10toast import ToastNotifier
import pystray
from PIL import Image

# =====================================================
#  PYINSTALLER UTILS
# =====================================================

def resource_path(path):
    try:
        return os.path.join(sys._MEIPASS, path)
    except Exception:
        return os.path.join(os.path.abspath("."), path)

# =====================================================
#  CONFIGURARE
# =====================================================

CAMERA_INDEX = 0

STABILIZARE_START = 1.5        # secunde dupa Start
TIMP_AVERTIZARE = 5            # secunde pana la notificare
ALERT_INTERVAL = 5            # pauza intre notificari
FEREASTRA_SMOOTH = 2           # sensibilitate mare (demo)

CALIBRARE_FILE = "calibrare.json"
STATS_FILE = "stats.txt"

# =====================================================
#  MEDIAPIPE
# =====================================================

mp_pose = mp.solutions.pose
pose = mp_pose.Pose()
draw = mp.solutions.drawing_utils

# =====================================================
#  VARIABILE GLOBALE
# =====================================================

camera_pornita = True
monitorizare = False

timp_corect = 0.0
timp_gresit = 0.0

last_time = time.time()
start_time_monitorizare = None
inceput_postura_gresita = None
last_alert = 0

unghiuri = []

PRAG_ATENTIE = 0
PRAG_APLECARE = 0

toaster = ToastNotifier()

# =====================================================
#  FUNCTII UTILE
# =====================================================

def unghi_gat(umar, ureche):
    dx = ureche[0] - umar[0]
    dy = ureche[1] - umar[1]
    return abs(np.degrees(np.arctan2(dy, dx)))

def notificare():
    toaster.show_toast(
        "Postura incorecta",
        "Indreapta spatele",
        duration=5,
        threaded=True
    )

# =====================================================
#  CALIBRARE
# =====================================================

def salveaza_calibrare():
    with open(CALIBRARE_FILE, "w") as f:
        json.dump({
            "PRAG_ATENTIE": PRAG_ATENTIE,
            "PRAG_APLECARE": PRAG_APLECARE
        }, f, indent=4)

def incarca_calibrare():
    global PRAG_ATENTIE, PRAG_APLECARE
    if os.path.exists(CALIBRARE_FILE):
        with open(CALIBRARE_FILE) as f:
            data = json.load(f)
            PRAG_ATENTIE = data["PRAG_ATENTIE"]
            PRAG_APLECARE = data["PRAG_APLECARE"]
        return True
    return False

def calibrare():
    global PRAG_ATENTIE, PRAG_APLECARE

    cap = cv2.VideoCapture(CAMERA_INDEX)
    valori = []
    start = time.time()

    while time.time() - start < 5:
        ret, frame = cap.read()
        if not ret:
            continue

        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = pose.process(img)

        if res.pose_landmarks:
            lm = res.pose_landmarks.landmark

            sL = [lm[mp_pose.PoseLandmark.LEFT_SHOULDER].x,
                  lm[mp_pose.PoseLandmark.LEFT_SHOULDER].y]
            eL = [lm[mp_pose.PoseLandmark.LEFT_EAR].x,
                  lm[mp_pose.PoseLandmark.LEFT_EAR].y]

            sR = [lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].x,
                  lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].y]
            eR = [lm[mp_pose.PoseLandmark.RIGHT_EAR].x,
                  lm[mp_pose.PoseLandmark.RIGHT_EAR].y]

            valori.append((unghi_gat(sL, eL) + unghi_gat(sR, eR)) / 2)

    cap.release()

    if valori:
        medie = sum(valori) / len(valori)
        PRAG_ATENTIE = medie + 5
        PRAG_APLECARE = medie + 12
        salveaza_calibrare()
        messagebox.showinfo("Calibrare", "Calibrare realizata cu succes.")

# =====================================================
#  STATISTICI
# =====================================================

def salveaza_statistici():
    azi = date.today().isoformat()
    total = timp_corect + timp_gresit

    if total == 0:
        linie = f"{azi} | fara monitorizare\n"
    else:
        linie = (
            f"{azi} | corect: {timp_corect:.1f}s | "
            f"gresit: {timp_gresit:.1f}s | "
            f"{timp_corect/total*100:.1f}%\n"
        )

    with open(STATS_FILE, "a", encoding="utf-8") as f:
        f.write(linie)

# =====================================================
#  MONITORIZARE POSTURA
# =====================================================

def monitorizare_camera():
    global timp_corect, timp_gresit, last_time
    global inceput_postura_gresita, last_alert

    cap = cv2.VideoCapture(CAMERA_INDEX)

    while camera_pornita:
        ret, frame = cap.read()
        if not ret:
            break

        now = time.time()
        dt = now - last_time
        last_time = now

        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = pose.process(img_rgb)
        img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        if res.pose_landmarks:
            draw.draw_landmarks(img, res.pose_landmarks, mp_pose.POSE_CONNECTIONS)
            lm = res.pose_landmarks.landmark

            sL = [lm[mp_pose.PoseLandmark.LEFT_SHOULDER].x,
                  lm[mp_pose.PoseLandmark.LEFT_SHOULDER].y]
            eL = [lm[mp_pose.PoseLandmark.LEFT_EAR].x,
                  lm[mp_pose.PoseLandmark.LEFT_EAR].y]
            sR = [lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].x,
                  lm[mp_pose.PoseLandmark.RIGHT_SHOULDER].y]
            eR = [lm[mp_pose.PoseLandmark.RIGHT_EAR].x,
                  lm[mp_pose.PoseLandmark.RIGHT_EAR].y]

            angle = (unghi_gat(sL, eL) + unghi_gat(sR, eR)) / 2
            unghiuri.append(angle)
            if len(unghiuri) > FEREASTRA_SMOOTH:
                unghiuri.pop(0)

            angle_s = sum(unghiuri) / len(unghiuri)

            if not monitorizare:
                culoare, text = (255, 0, 0), "PREVIEW"
                inceput_postura_gresita = None

            elif time.time() - start_time_monitorizare < STABILIZARE_START:
                culoare, text = (180, 180, 180), "STABILIZING..."

            elif angle_s > PRAG_APLECARE:
                culoare, text = (0, 0, 255), "POSTURA INCORECTA"
                timp_gresit += dt
                if inceput_postura_gresita is None:
                    inceput_postura_gresita = now
                if now - inceput_postura_gresita >= TIMP_AVERTIZARE:
                    if now - last_alert >= ALERT_INTERVAL:
                        notificare()
                        last_alert = now

            elif angle_s > PRAG_ATENTIE:
                culoare, text = (0, 255, 255), "ATENTIE"
                timp_gresit += dt

            else:
                culoare, text = (0, 255, 0), "POSTURA CORECTA"
                timp_corect += dt
                inceput_postura_gresita = None

            h, w, _ = img.shape
            for s, e in [(sL, eL), (sR, eR)]:
                cv2.line(img,
                         (int(s[0]*w), int(s[1]*h)),
                         (int(e[0]*w), int(e[1]*h)),
                         culoare, 3)

            cv2.putText(img, text, (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, culoare, 3)
            cv2.putText(img, f"Unghi: {angle_s:.1f}",
                        (30, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (255, 255, 255), 2)

        cv2.imshow("Corector postura", img)
        if cv2.waitKey(10) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

# =====================================================
#  CONTROL
# =====================================================

def start():
    global monitorizare, start_time_monitorizare
    global unghiuri, last_time, inceput_postura_gresita, last_alert

    monitorizare = True
    start_time_monitorizare = time.time()
    unghiuri.clear()
    last_time = time.time()
    inceput_postura_gresita = None
    last_alert = 0

def pause():
    global monitorizare
    monitorizare = False

def exit_app():
    global camera_pornita
    camera_pornita = False
    salveaza_statistici()
    os._exit(0)

# =====================================================
#  SYSTEM TRAY
# =====================================================

def setup_tray():
    image = Image.open(resource_path("icon.ico"))
    menu = pystray.Menu(
        pystray.MenuItem("Start", lambda i, x: start()),
        pystray.MenuItem("Pauza", lambda i, x: pause()),
        pystray.MenuItem("Calibrare", lambda i, x: calibrare()),
        pystray.MenuItem("Exit", lambda i, x: exit_app())
    )
    icon = pystray.Icon("Postura", image, "Corector Postura", menu)
    icon.run()

# =====================================================
#  START APLICATIE
# =====================================================

root = tk.Tk()
root.withdraw()

if not incarca_calibrare():
    messagebox.showinfo(
        "Calibrare",
        "Stai drept, cu spatele lipit de scaun.\nCalibrarea dureaza 5 secunde."
    )
    calibrare()

Thread(target=monitorizare_camera, daemon=True).start()
setup_tray()
