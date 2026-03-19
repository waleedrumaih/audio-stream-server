#include "AudioTools.h"
#include "AudioTools/AudioLibs/I2SCodecStream.h"
#include "AudioBoard.h"
#include <Wire.h>
#include <WiFi.h>
#include <WebSocketsClient.h>  // install "WebSockets" by Markus Sattler

const char* SSID     = "TOTOLINK_EX1800T";
const char* PASSWORD = "W.0504449992";
const char* WS_HOST  = "192.168.100.44";  // ← your Mac local IP
const int   WS_PORT  = 8765;
const char* WS_PATH  = "/audio";

#define ES8388_ADDR        0x10
#define ES8388_ADCCONTROL1 0x09

void es8388_write(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(ES8388_ADDR);
  Wire.write(reg); Wire.write(val);
  Wire.endTransmission();
}

I2SCodecStream  i2sStream(AudioKitEs8388V1);
WebSocketsClient ws;
const int AUDIO_CHUNK = 512;
uint8_t   audioBuffer[AUDIO_CHUNK];
bool      wsConnected = false;

void onWSEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      wsConnected = true;
      Serial.println("✅ WebSocket connected!");
      break;
    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.println("⚠️ WebSocket disconnected!");
      break;
    case WStype_ERROR:
      Serial.println("❌ WebSocket error!");
      break;
    default:
      break;
  }
}

void connectWiFi() {
  WiFi.begin(SSID, PASSWORD);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.print("\n✅ WiFi IP: ");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  Wire.begin(33, 32);
  AudioLogger::instance().begin(Serial, AudioLogger::Error);

  connectWiFi();

  // ─── Connect WebSocket ────────────────────────────
  ws.begin(WS_HOST, WS_PORT, WS_PATH);
  ws.onEvent(onWSEvent);
  ws.setReconnectInterval(3000);
  Serial.println("🔌 Connecting to WebSocket server...");

  // ─── Init Codec ───────────────────────────────────
  auto cfg = i2sStream.defaultConfig(RX_MODE);
  cfg.sample_rate     = 16000;
  cfg.channels        = 2;
  cfg.bits_per_sample = 16;
  cfg.input_device    = ADC_INPUT_LINE2;
  i2sStream.begin(cfg);
  es8388_write(ES8388_ADCCONTROL1, 0x44);

  Serial.println("🎙️ Ready!");
}

void loop() {
  ws.loop();  // keep WebSocket alive

  if (wsConnected) {
    int bytesRead = i2sStream.readBytes(audioBuffer, AUDIO_CHUNK);
    if (bytesRead > 0) {
      ws.sendBIN(audioBuffer, bytesRead);
    }
  }
}