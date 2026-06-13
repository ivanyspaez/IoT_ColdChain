#include <WiFi.h>
#include <HTTPClient.h>

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#include <DFRobot_SHT20.h>

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
"Familia sepulveda_2.4G";

const char* WIFI_PASSWORD =
"9611170412";

const char* SERVER_URL =
"http://192.168.2.12:8000/telemetry";

const char* DEVICE_ID =
"esp32-coldchain-001";

// Pega aquí la API Key que te muestra la web al registrar el producto
const char* API_KEY =
"z8JVeqyHrDpDv90asn8dwtM3yEF_LDIAgcYpNH0XR8k";

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
// OLED
// ======================

void updateDisplay()
{
    display.clearDisplay();

    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(0, 0);
    display.println("ColdChain IoT");

    display.drawLine(
        0,
        10,
        127,
        10,
        SSD1306_WHITE
    );

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
    WiFi.begin(
        WIFI_SSID,
        WIFI_PASSWORD
    );

    Serial.print("Conectando");

    while (
        WiFi.status() != WL_CONNECTED
    )
    {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("WiFi conectado");

    wifiStatus = "OK";

    Serial.print("IP ESP32: ");
    Serial.println(
        WiFi.localIP()
    );

    updateDisplay();
}

// ======================
// TELEMETRIA
// ======================

void sendTelemetry()
{
    if (
        WiFi.status() != WL_CONNECTED
    )
    {
        wifiStatus = "FAIL";
        updateDisplay();
        return;
    }

    temperature =
        sht20.readTemperature();

    humidity =
        sht20.readHumidity();

    if (
        isnan(temperature) ||
        isnan(humidity)
    )
    {
        Serial.println("Error leyendo SHT20");
        httpStatus = "SHT ERR";
        updateDisplay();
        return;
    }

    Serial.println();
    Serial.println("Lecturas SHT20");

    Serial.print("Temperatura: ");
    Serial.print(temperature);
    Serial.println(" C");

    Serial.print("Humedad: ");
    Serial.print(humidity);
    Serial.println(" %");

    String json =
        "{"
        "\"device_id\":\"" + String(DEVICE_ID) + "\","
        "\"temperature\":" + String(temperature, 1) + ","
        "\"humidity\":" + String(humidity, 1) + ","
        "\"battery\":95,"
        "\"status\":\"OK\""
        "}";

    Serial.println();
    Serial.println("Enviando:");
    Serial.println(json);

    HTTPClient http;

    http.begin(SERVER_URL);

    http.addHeader(
        "Content-Type",
        "application/json"
    );

    http.addHeader(
        "X-API-KEY",
        API_KEY
    );

    int code = http.POST(json);

    Serial.print("HTTP CODE: ");
    Serial.println(code);

    if (code >= 200 && code < 300)
    {
        httpStatus = "OK";

        String response = http.getString();

        Serial.println();
        Serial.println("RESPUESTA:");
        Serial.println(response);
    }
    else
    {
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

    if (
        !display.begin(
            SSD1306_SWITCHCAPVCC,
            0x3C
        )
    )
    {
        Serial.println("OLED NO DETECTADA");
        while (true);
    }

    // Si la ves invertida, esta linea puede ayudarte:
    display.ssd1306_command(0xC0);

    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("Iniciando...");
    display.display();

    sht20.initSHT20();
    delay(100);
    sht20.checkSHT20();

    Serial.println("SHT20 listo");

    connectWiFi();

    randomSeed(millis());

    updateDisplay();
}

// ======================
// LOOP
// ======================

void loop()
{
    if (
        millis() - lastSend >= interval
    )
    {
        lastSend = millis();
        sendTelemetry();
    }
}