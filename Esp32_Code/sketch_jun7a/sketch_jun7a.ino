#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Arduino_JSON.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <time.h>
#include "mbedtls/md.h"

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ====== WIFI ======
const char* WIFI_SSID     = "Familia sepulveda_2.4G";
const char* WIFI_PASSWORD = "9611170412";

// ====== BACKEND ======
// Cambia esto por la IP o dominio donde corre tu Docker.
// Ejemplo local: "https://192.168.1.50:8000/api/telemetry"
const char* API_URL = "https://TU_SERVIDOR:8000/api/telemetry";

// ====== DISPOSITIVO ======
const char* DEVICE_ID     = "esp32-coldchain-001";
const char* DEVICE_SECRET = "cambia-esta-clave-larga-y-unica";

// ====== ESTADO ======
float temperatureC = 4.2;
float humidityPct   = 67.0;

unsigned long lastSendMs = 0;
const unsigned long SEND_INTERVAL_MS = 10000;

String lastStatus = "BOOT";
String lastIp = "-";

String hmacSha256Hex(const String& message, const String& key) {
  byte hmacResult[32];
  const mbedtls_md_info_t* mdInfo = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);

  if (mbedtls_md_setup(&ctx, mdInfo, 1) != 0) {
    mbedtls_md_free(&ctx);
    return "";
  }

  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)key.c_str(), key.length());
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)message.c_str(), message.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);

  char out[65];
  for (int i = 0; i < 32; i++) {
    sprintf(&out[i * 2], "%02x", hmacResult[i]);
  }
  out[64] = '\0';
  return String(out);
}

void drawStatus(const String& line1, const String& line2, const String& line3, const String& line4) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println(line1);
  display.println(line2);
  display.println(line3);
  display.println(line4);
  display.display();
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  drawStatus("Conectando WiFi...", WIFI_SSID, "Esperando red", "");

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
  }

  if (WiFi.status() == WL_CONNECTED) {
    lastIp = WiFi.localIP().toString();
    lastStatus = "WIFI OK";
  } else {
    lastStatus = "WIFI FAIL";
  }
}

void syncTime() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov", "time.google.com");

  struct tm timeinfo;
  unsigned long start = millis();
  while (!getLocalTime(&timeinfo) && millis() - start < 15000) {
    delay(300);
  }
}

time_t nowEpoch() {
  time_t now = time(nullptr);
  return now;
}

void readDummyTelemetry() {
  temperatureC += random(-6, 7) * 0.05;
  humidityPct   += random(-10, 11) * 0.10;

  temperatureC = constrain(temperatureC, 2.0, 8.0);
  humidityPct   = constrain(humidityPct, 50.0, 90.0);
}

bool sendTelemetry() {
  if (WiFi.status() != WL_CONNECTED) {
    lastStatus = "SIN WIFI";
    return false;
  }

  time_t ts = nowEpoch();
  if (ts < 1700000000) {
    lastStatus = "SIN NTP";
    return false;
  }

  String body =
  "{"
  "\"device_id\":\"" + String(DEVICE_ID) + "\","
  "\"temperature\":" + String(temperatureC, 1) + ","
  "\"humidity\":" + String(humidityPct, 1) + ","
  "\"ts\":" + String((uint32_t)ts) +
  "}";

  String message = String(DEVICE_ID) + "." + String((uint32_t)ts) + "." + body;
  String signature = hmacSha256Hex(message, DEVICE_SECRET);

  WiFiClientSecure client;
  client.setInsecure(); // Para pruebas. En producción reemplaza por client.setCACert(root_ca);

  HTTPClient http;
  if (!http.begin(client, API_URL)) {
    lastStatus = "HTTP BEGIN FAIL";
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("X-Timestamp", String((uint32_t)ts));
  http.addHeader("X-Signature", signature);

  int code = http.POST(body);
  String resp = http.getString();
  http.end();

  if (code >= 200 && code < 300) {
    lastStatus = "ENVIO OK";
    return true;
  } else {
    lastStatus = "HTTP " + String(code);
    return false;
  }
}

void setup() {
  Serial.begin(115200);
  randomSeed(esp_random());

  Wire.begin(21, 22);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    while (true) {}
  }

  // Tu corrección que ya funcionó
  display.ssd1306_command(0xA0);
  display.ssd1306_command(0xC8);

  drawStatus("Iniciando...", "SSD1312", "ESP32 IoT", "");

  connectWiFi();
  syncTime();

  drawStatus(
    "Listo",
    String("IP: ") + lastIp,
    String("Estado: ") + lastStatus,
    "Primer envio..."
  );

  readDummyTelemetry();
  sendTelemetry();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    syncTime();
  }

  if (millis() - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = millis();

    readDummyTelemetry();
    bool ok = sendTelemetry();

    drawStatus(
      String("Temp: ") + String(temperatureC, 1) + " C",
      String("Humedad: ") + String(humidityPct, 1) + " %",
      String("IP: ") + lastIp,
      ok ? "Enviado OK" : ("Error: " + lastStatus)
    );
  }
}