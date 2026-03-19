import serial
import wave
import glob
import sys
import time
import struct

def find_port():
    ports = glob.glob('/dev/cu.usb*') + glob.glob('/dev/cu.SLAB*')
    if not ports:
        print("❌ ESP32 not found!")
        sys.exit(1)
    print(f"✅ Found: {ports[0]}")
    return ports[0]

PORT        = find_port()
BAUD        = 921600
SAMPLE_RATE = 16000
CHANNELS    = 2
DURATION    = 10
OUTPUT      = "linein_recording.wav"
TARGET_LEVEL = 0.7  # ← target 70% of max volume (adjust 0.1-1.0)

print(f"🎙️  Plug headset into LINEIN jack")
print(f"⏱️  Recording for {DURATION} seconds...")
print(f"💾  Saving to: {OUTPUT}\n")

ser = serial.Serial(PORT, BAUD, timeout=2)
time.sleep(2)
ser.reset_input_buffer()

raw_samples = []
total = SAMPLE_RATE * CHANNELS * 2 * DURATION
got   = 0

while got < total:
    chunk = ser.read(1024)
    if chunk:
        raw_samples.append(chunk)
        got += len(chunk)
        pct = int((got / total) * 40)
        bar = '█' * pct + '░' * (40 - pct)
        print(f"\r  [{bar}] {got*100//total}%", end='')

ser.close()
print("\n\n🔊 Auto-normalizing...")

# ─── Decode samples ──────────────────────────────────
raw = b''.join(raw_samples)
samples = list(struct.unpack('<' + 'h' * (len(raw)//2), raw))

# ─── Find peak level ─────────────────────────────────
peak = max(abs(s) for s in samples)
print(f"📊 Peak level   : {peak} / 32767 ({peak*100//32767}%)")

# ─── Calculate auto gain ─────────────────────────────
if peak == 0:
    print("❌ No signal detected!")
    sys.exit(1)

auto_gain = (32767 * TARGET_LEVEL) / peak
print(f"📊 Auto gain    : {auto_gain:.2f}x")
print(f"📊 Target level : {int(TARGET_LEVEL*100)}%")

# ─── Apply auto gain ─────────────────────────────────
normalized = [max(-32768, min(32767, int(s * auto_gain))) for s in samples]

# ─── Save WAV ────────────────────────────────────────
wav = wave.open(OUTPUT, 'wb')
wav.setnchannels(CHANNELS)
wav.setsampwidth(2)
wav.setframerate(SAMPLE_RATE)
wav.writeframes(struct.pack('<' + 'h' * len(normalized), *normalized))
wav.close()

print(f"\n✅ Saved: {OUTPUT}")
print(f"▶️  Playing back...\n")

import subprocess
subprocess.run(['afplay', OUTPUT])