#include <WiFi.h>
#include <PubSubClient.h>

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

const char* WIFI_SSID = "FLOZANOG";
const char* WIFI_PASSWORD = "Kj.1110**";

// IP de tu PC / host Docker, no la del contenedor
const char* MQTT_SERVER = "192.168.80.19";
const uint16_t MQTT_PORT = 1883;

const char* DEVICE_ID = "esp32-coldchain-001";
const char* TOPIC_TELEMETRY = "coldchain/esp32-coldchain-001/telemetry";

// Si después activas autenticación en Mosquitto, descomenta estas dos líneas:
// const char* MQTT_USER = "coldchain";
// const char* MQTT_PASSWORD = "coldchain123";

// ======================
// CLIENTES
// ======================

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// ======================
// VARIABLES
// ======================

float temperature = 0;
float humidity = 0;

String wifiStatus = "DESC";
String mqttStatus = "OFF";
String httpStatus = "OFF";

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

    display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

    // Fila 1
    display.setCursor(0, 14);
    display.print("Temp:");
    display.print(temperature, 1);
    display.print(" C");

    // Fila 2: mitad izquierda / derecha
    display.setCursor(0, 26);
    display.print("Hum:");
    display.print(humidity, 1);
    display.print(" %");

    display.setCursor(70, 26);
    display.print("WiFi:");
    display.print(wifiStatus);

    // Fila 3: mitad izquierda / derecha
    display.setCursor(0, 38);
    display.print("MQTT:");
    display.print(mqttStatus);

    display.setCursor(70, 38);
    display.print("HTTP:");
    display.print(httpStatus);

    // Fila 4 completa
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
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.print("Conectando WiFi");

    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.println("WiFi conectado");

    wifiStatus = "OK";

    Serial.print("IP ESP32: ");
    Serial.println(WiFi.localIP());

    Serial.print("Gateway: ");
    Serial.println(WiFi.gatewayIP());

    Serial.print("DNS: ");
    Serial.println(WiFi.dnsIP());

    updateDisplay();
}

// ======================
// MQTT
// ======================

void connectMQTT()
{
    mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
    mqttClient.setBufferSize(256);

    while (!mqttClient.connected())
    {
        Serial.println("Conectando MQTT...");

        String clientId = String(DEVICE_ID) + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);

        // Broker actual con allow_anonymous true
        bool ok = mqttClient.connect(clientId.c_str());

        // Si luego activas autenticación:
        // bool ok = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD);

        if (ok)
        {
            Serial.println("MQTT conectado");
            mqttStatus = "OK";
        }
        else
        {
            Serial.print("MQTT error: ");
            Serial.println(mqttClient.state());

            mqttStatus = "FAIL";
            updateDisplay();
            delay(3000);
        }
    }

    updateDisplay();
}

// ======================
// TELEMETRIA MQTT
// ======================

void sendTelemetry()
{
    if (WiFi.status() != WL_CONNECTED)
    {
        wifiStatus = "FAIL";
        updateDisplay();
        return;
    }

    if (!mqttClient.connected())
    {
        connectMQTT();
    }

    temperature = sht20.readTemperature();
    humidity = sht20.readHumidity();

    if (isnan(temperature) || isnan(humidity))
    {
        Serial.println("Error leyendo SHT20");
        mqttStatus = "SHT ERR";
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

    Serial.println();
    Serial.println("Lecturas SHT20");
    Serial.print("Temperatura: ");
    Serial.print(temperature);
    Serial.println(" C");
    Serial.print("Humedad: ");
    Serial.print(humidity);
    Serial.println(" %");

    Serial.println();
    Serial.println("Publicando MQTT:");
    Serial.println(json);

    bool ok = mqttClient.publish(
        TOPIC_TELEMETRY,
        json.c_str()
    );

    if (ok)
    {
        mqttStatus = "OK";
        httpStatus = "OFF";
        Serial.println("MQTT OK");
    }
    else
    {
        mqttStatus = "ERR";
        Serial.print("MQTT FAIL, state=");
        Serial.println(mqttClient.state());
    }

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

    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C))
    {
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
    connectMQTT();

    mqttStatus = "OK";
    httpStatus = "OFF";

    updateDisplay();
}

// ======================
// LOOP
// ======================

void loop()
{
    if (WiFi.status() != WL_CONNECTED)
    {
        wifiStatus = "FAIL";
        connectWiFi();
    }

    if (!mqttClient.connected())
    {
        connectMQTT();
    }

    mqttClient.loop();

    if (millis() - lastSend >= interval)
    {
        lastSend = millis();
        sendTelemetry();
    }
}