#include <WiFi.h>
#include <HTTPClient.h>

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#include <DFRobot_SHT20.h>
#include <time.h>
#include "mbedtls/md.h"

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    &Wire,
    -1
);

DFRobot_SHT20 sht20;

// ======================
// CONFIG
// ======================

const char* WIFI_SSID =
"FLOZANOG";

const char* WIFI_PASSWORD =
"Kj.1110**";

const char* SERVER_URL =
"http://192.168.80.19:8000/telemetry";

const char* DEVICE_ID =
"esp32-coldchain-001";

// Copia exactamente esto desde el dashboard
const char* API_KEY =
"WV5SQA9AA2K7RwHVZXhwqWPSpEOJqgLZNTv5zczjaLg";

// Copia exactamente esto desde el dashboard
const char* DEVICE_SECRET =
"z524zp-b_LfYnOUWYL-2vUG0KIQ7AZCOk24M3E6N1E5RHjs1kDgDit0swcM86A2F";

// ======================
// VARIABLES
// ======================

float temperature = 0;
float humidity = 0;

String wifiStatus = "DESC";
String httpStatus = "---";

unsigned long lastSend = 0;
const unsigned long interval = 10000;

// ======================
// HMAC
// ======================

String hmacSha256Hex(const String& message, const String& key) {
    byte hmacResult[32];

    const mbedtls_md_info_t* mdInfo =
        mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);

    mbedtls_md_context_t ctx;
    mbedtls_md_init(&ctx);

    if (mbedtls_md_setup(&ctx, mdInfo, 1) != 0) {
        mbedtls_md_free(&ctx);
        return "";
    }

    mbedtls_md_hmac_starts(
        &ctx,
        (const unsigned char*)key.c_str(),
        key.length()
    );

    mbedtls_md_hmac_update(
        &ctx,
        (const unsigned char*)message.c_str(),
        message.length()
    );

    mbedtls_md_hmac_finish(&ctx, hmacResult);
    mbedtls_md_free(&ctx);

    char out[65];
    for (int i = 0; i < 32; i++) {
        sprintf(&out[i * 2], "%02x", hmacResult[i]);
    }
    out[64] = '\0';

    return String(out);
}

// ======================
// TIME
// ======================

void syncTime() {
    configTime(
        0,
        0,
        "pool.ntp.org",
        "time.nist.gov",
        "time.google.com"
    );

    struct tm timeinfo;
    unsigned long start = millis();

    while (!getLocalTime(&timeinfo) && millis() - start < 15000) {
        delay(300);
    }
}

time_t nowEpoch() {
    return time(nullptr);
}

// ======================
// OLED
// ======================

void updateDisplay()
{
    display.clearDisplay();

    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(0, 0);
    display.println("ColdChain IoT");

    display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

    display.setCursor(0, 16);
    display.print("Temp: ");
    display.print(temperature, 1);
    display.println(" C");

    display.setCursor(0, 28);
    display.print("Hum : ");
    display.print(humidity, 1);
    display.println(" %");

    display.setCursor(0, 40);
    display.print("WiFi:");
    display.println(wifiStatus);

    display.setCursor(70, 40);
    display.print("HTTP:");
    display.println(httpStatus);

    display.setCursor(0, 54);
    display.print("ID:");
    display.print(DEVICE_ID);

    display.display();
}

// ======================
// WIFI
// ======================

void connectWiFi()
{
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.print("Conectando");

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("WiFi conectado");

    wifiStatus = "OK";

    Serial.print("IP ESP32: ");
    Serial.println(WiFi.localIP());

    updateDisplay();
}

// ======================
// TELEMETRIA
// ======================

void sendTelemetry()
{
    if (WiFi.status() != WL_CONNECTED) {
        wifiStatus = "FAIL";
        updateDisplay();
        return;
    }

    time_t ts = nowEpoch();
    if (ts < 1700000000) {
        Serial.println("NTP no sincronizado");
        httpStatus = "NTP";
        updateDisplay();
        return;
    }

    temperature = sht20.readTemperature();
    humidity = sht20.readHumidity();

    if (isnan(temperature) || isnan(humidity)) {
        Serial.println("Error leyendo SHT20");
        httpStatus = "SHT ERR";
        updateDisplay();
        return;
    }

    String json =
        "{"
        "\"device_id\":\"" + String(DEVICE_ID) + "\","
        "\"temperature\":" + String(temperature, 1) + ","
        "\"humidity\":" + String(humidity, 1) + ","
        "\"battery\":95,"
        "\"status\":\"OK\""
        "}";

    String message =
        String(DEVICE_ID) + "." +
        String((uint32_t)ts) + "." +
        json;

    String signature =
        hmacSha256Hex(message, DEVICE_SECRET);

    Serial.println();
    Serial.println("Lecturas SHT20");
    Serial.print("Temperatura: ");
    Serial.print(temperature);
    Serial.println(" C");
    Serial.print("Humedad: ");
    Serial.print(humidity);
    Serial.println(" %");

    Serial.println();
    Serial.println("Enviando:");
    Serial.println(json);
    Serial.print("TIMESTAMP: ");
    Serial.println((uint32_t)ts);
    Serial.print("SIGNATURE: ");
    Serial.println(signature);

    HTTPClient http;
    http.begin(SERVER_URL);

    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-KEY", API_KEY);
    http.addHeader("X-Timestamp", String((uint32_t)ts));
    http.addHeader("X-Signature", signature);

    int code = http.POST(json);

    Serial.print("HTTP CODE: ");
    Serial.println(code);

    if (code >= 200 && code < 300) {
        httpStatus = "OK";
        String response = http.getString();

        Serial.println();
        Serial.println("RESPUESTA:");
        Serial.println(response);
    } else {
        httpStatus = "ERR";
        Serial.println("Error enviando telemetria");
    }

    http.end();
    updateDisplay();
}

// ======================
// SETUP
// ======================

void setup()
{
    Serial.begin(115200);
    delay(1000);

    Wire.begin(21, 22);

    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("OLED NO DETECTADA");
        while (true);
    }

    // Mantiene tu orientación actual
    display.ssd1306_command(0xC0);

    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("Iniciando...");
    display.display();

    sht20.initSHT20();
    delay(100);

    Serial.println("SHT20 listo");

    connectWiFi();
    syncTime();

    updateDisplay();
}

// ======================
// LOOP
// ======================

void loop()
{
    if (millis() - lastSend >= interval) {
        lastSend = millis();
        sendTelemetry();
    }
}