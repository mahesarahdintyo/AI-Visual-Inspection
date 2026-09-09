#include <Arduino.h>

#define LED_GREEN 2
#define LED_RED 4
#define BUZZER 5
#define RELAY_PIN 18

void setup() {
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_RED, OUTPUT);
    pinMode(BUZZER, OUTPUT);
    pinMode(RELAY_PIN, OUTPUT);

    // Standby: LED Hijau ON, Relay OFF
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_RED, LOW);
    digitalWrite(BUZZER, LOW);
    digitalWrite(RELAY_PIN, LOW);

    Serial.begin(115200);
}

void loop() {
    if (Serial.available() > 0) {
        String command = Serial.readStringUntil('\n');
        command.trim();

        if (command == "OK") {
            digitalWrite(LED_GREEN, HIGH);
            digitalWrite(LED_RED, LOW);
            digitalWrite(BUZZER, LOW);
            digitalWrite(RELAY_PIN, LOW);
        } 
        else if (command == "NG") {
            digitalWrite(LED_GREEN, LOW);
            digitalWrite(LED_RED, HIGH);
            digitalWrite(BUZZER, HIGH);
            digitalWrite(RELAY_PIN, HIGH);
        }
    }
}