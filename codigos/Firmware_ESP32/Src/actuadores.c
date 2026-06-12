#include "actuadores.h"
#include "configuracion.h"
#include "control_dimmer.h"

#include "driver/gpio.h"
#include "driver/ledc.h"

#include "esp_log.h"

#include <stdbool.h>
#include <stdint.h>

static const char *TAG = "actuadores";

static uint8_t foco_nivel_anterior = 255;
static bool bomba_anterior = false;
static bool ventilador_anterior = false;
static uint8_t velocidad_anterior = 0;
static bool ultima_alarma_visual = false;

static void motor_set_pwm(uint8_t velocidad);

void actuadores_iniciar(void)
{
    // Bomba
    gpio_reset_pin(PIN_BOMBA);
    gpio_set_direction(PIN_BOMBA, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_BOMBA, 0);

    // TRIAC foco: queda apagado. El manejo fino lo hace control_dimmer.c
    gpio_reset_pin(PIN_FOCO_TRIAC);
    gpio_set_direction(PIN_FOCO_TRIAC, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_FOCO_TRIAC, 0);

    // Alarma visual
    gpio_reset_pin(PIN_ALARMA_VISUAL);
    gpio_set_direction(PIN_ALARMA_VISUAL, GPIO_MODE_OUTPUT);

#if ALARMA_VISUAL_LOGICA_INVERTIDA
    gpio_set_level(PIN_ALARMA_VISUAL, 1);  // apagada
#else
    gpio_set_level(PIN_ALARMA_VISUAL, 0);  // apagada
#endif

    // Motor portón - dirección
    gpio_reset_pin(PIN_MOTOR_IN1);
    gpio_reset_pin(PIN_MOTOR_IN2);

    gpio_set_direction(PIN_MOTOR_IN1, GPIO_MODE_OUTPUT);
    gpio_set_direction(PIN_MOTOR_IN2, GPIO_MODE_OUTPUT);

    gpio_set_level(PIN_MOTOR_IN1, 0);
    gpio_set_level(PIN_MOTOR_IN2, 0);

    // PWM ventilador
    ledc_timer_config_t timer_pwm_vent = {
        .speed_mode = PWM_VENT_MODO,
        .timer_num = PWM_VENT_TIMER,
        .duty_resolution = PWM_VENT_RES,
        .freq_hz = PWM_VENT_FREQ_HZ,
        .clk_cfg = LEDC_AUTO_CLK
    };

    ledc_timer_config(&timer_pwm_vent);

    ledc_channel_config_t canal_pwm_vent = {
        .gpio_num = PIN_VENTILADOR,
        .speed_mode = PWM_VENT_MODO,
        .channel = PWM_VENT_CANAL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = PWM_VENT_TIMER,
        .duty = 0,
        .hpoint = 0
    };

    ledc_channel_config(&canal_pwm_vent);

    // PWM motor portón
    ledc_timer_config_t timer_pwm_motor = {
        .speed_mode = PWM_MOTOR_MODO,
        .timer_num = PWM_MOTOR_TIMER,
        .duty_resolution = PWM_MOTOR_RES,
        .freq_hz = PWM_MOTOR_FREQ_HZ,
        .clk_cfg = LEDC_AUTO_CLK
    };

    ledc_timer_config(&timer_pwm_motor);

    ledc_channel_config_t canal_pwm_motor = {
        .gpio_num = PIN_MOTOR_PWM,
        .speed_mode = PWM_MOTOR_MODO,
        .channel = PWM_MOTOR_CANAL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = PWM_MOTOR_TIMER,
        .duty = 0,
        .hpoint = 0
    };

    ledc_channel_config(&canal_pwm_motor);

    foco_nivel_anterior = 255;
    bomba_anterior = false;
    ventilador_anterior = false;
    velocidad_anterior = 0;
    ultima_alarma_visual = false;

    ESP_LOGI(TAG, "Actuadores inicializados");
}

void actuadores_set_foco(uint8_t nivel)
{
    if (nivel > 100) {
        nivel = 100;
    }

    control_dimmer_set_nivel(nivel);

    if (nivel != foco_nivel_anterior) {
        ESP_LOGI(TAG, "Foco nivel logico: %u%%", nivel);
        foco_nivel_anterior = nivel;
    }
}

void actuadores_set_bomba(bool encender)
{
    gpio_set_level(PIN_BOMBA, encender ? 1 : 0);

    if (encender != bomba_anterior) {
        ESP_LOGI(TAG, "Bomba: %s", encender ? "ON" : "OFF");
        bomba_anterior = encender;
    }
}

void actuadores_set_ventilador(bool encender, uint8_t velocidad)
{
    if (velocidad > 100) {
        velocidad = 100;
    }

    uint32_t duty = encender ? ((uint32_t)velocidad * PWM_DUTY_MAX) / 100 : 0;

    ledc_set_duty(PWM_VENT_MODO, PWM_VENT_CANAL, duty);
    ledc_update_duty(PWM_VENT_MODO, PWM_VENT_CANAL);

    if (encender != ventilador_anterior || velocidad != velocidad_anterior) {
        ESP_LOGI(TAG, "Ventilador: %s, velocidad: %u%%", encender ? "ON" : "OFF", velocidad);

        ventilador_anterior = encender;
        velocidad_anterior = velocidad;
    }
}

void actuadores_set_alarma_visual(bool encendida)
{
#if ALARMA_VISUAL_LOGICA_INVERTIDA
    gpio_set_level(PIN_ALARMA_VISUAL, encendida ? 0 : 1);
#else
    gpio_set_level(PIN_ALARMA_VISUAL, encendida ? 1 : 0);
#endif

    if (encendida != ultima_alarma_visual) {
        ESP_LOGI(TAG, "Alarma visual: %s", encendida ? "ON" : "OFF");
        ultima_alarma_visual = encendida;
    }
}

static void motor_set_pwm(uint8_t velocidad)
{
    if (velocidad > 100) {
        velocidad = 100;
    }

    uint32_t duty = ((uint32_t)PWM_DUTY_MAX * velocidad) / 100;

    ledc_set_duty(PWM_MOTOR_MODO, PWM_MOTOR_CANAL, duty);
    ledc_update_duty(PWM_MOTOR_MODO, PWM_MOTOR_CANAL);
}

void actuadores_motor_detener(void)
{
    motor_set_pwm(0);
    gpio_set_level(PIN_MOTOR_IN1, 0);
    gpio_set_level(PIN_MOTOR_IN2, 0);

    ESP_LOGI(TAG, "Motor porton: STOP");
}

void actuadores_motor_abrir(uint8_t velocidad)
{
    gpio_set_level(PIN_MOTOR_IN1, 1);
    gpio_set_level(PIN_MOTOR_IN2, 0);
    motor_set_pwm(velocidad);

    ESP_LOGI(TAG, "Motor porton: ABRIR %u%%", velocidad);
}

void actuadores_motor_cerrar(uint8_t velocidad)
{
    gpio_set_level(PIN_MOTOR_IN1, 0);
    gpio_set_level(PIN_MOTOR_IN2, 1);
    motor_set_pwm(velocidad);

    ESP_LOGI(TAG, "Motor porton: CERRAR %u%%", velocidad);
}