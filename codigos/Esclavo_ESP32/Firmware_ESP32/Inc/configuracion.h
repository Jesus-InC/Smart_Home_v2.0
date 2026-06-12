#ifndef MAIN_INC_CONFIGURACION_H_
#define MAIN_INC_CONFIGURACION_H_

#include "driver/gpio.h"
#include "driver/ledc.h"

// Broker MQTT en la Raspberry Pi
#define MQTT_URI        "mqtt://192.168.1.19:1883"

// AP minimo para provision WiFi
#define PORTAL_WIFI_SSID        "SmartHome-Config"
#define PORTAL_WIFI_PASSWORD    "12345678"
#define PORTAL_WIFI_CANAL       1
#define PORTAL_WIFI_MAX_CONEX   4
#define WIFI_REINTENTOS_MAX     8

// Sistema general
#define TOPICO_SISTEMA_ESTOP              "casa/sistema/estop"
#define TOPICO_SISTEMA_ESTOP_CMD          "casa/sistema/estop/cmd"
#define TOPICO_SISTEMA_ESTOP_ESTADO       "casa/sistema/estop/estado"
#define TOPICO_SISTEMA_ESTADO_SEGURO      "casa/sistema/estado_seguro"
#define TOPICO_SISTEMA_CONEXION_ESTADO    "casa/sistema/conexion/estado"
#define TOPICO_SISTEMA_WIFI_ESTADO        "casa/sistema/wifi/estado"
#define TOPICO_SISTEMA_WIFI_IP            "casa/sistema/wifi/ip"
#define TOPICO_SISTEMA_WIFI_RSSI          "casa/sistema/wifi/rssi"
#define TOPICO_SISTEMA_WIFI_OLVIDAR_CMD   "casa/sistema/wifi/olvidar/cmd"
#define TOPICO_SISTEMA_FALLA_EVENTO       "casa/sistema/falla/evento"
#define TOPICO_SISTEMA_FALLA_ULTIMA       "casa/sistema/falla/ultima"
#define TOPICO_SISTEMA_FALLA_CONTADOR     "casa/sistema/falla/contador"

// Interior - modo
#define TOPICO_INTERIOR_MODO_CMD          "casa/interior/modo/cmd"
#define TOPICO_INTERIOR_MODO_ESTADO       "casa/interior/modo/estado"

// Interior - foco
#define TOPICO_INTERIOR_FOCO_CMD          "casa/interior/foco/cmd"
#define TOPICO_INTERIOR_FOCO_ESTADO       "casa/interior/foco/estado"
#define TOPICO_INTERIOR_FOCO_OVERRIDE     "casa/interior/foco/override"

// Interior - ventilador
#define TOPICO_INTERIOR_VENT_CMD          "casa/interior/vent/cmd"
#define TOPICO_INTERIOR_VENT_ESTADO       "casa/interior/vent/estado"
#define TOPICO_INTERIOR_VENT_OVERRIDE     "casa/interior/vent/override"

// Interior - bomba
#define TOPICO_INTERIOR_BOMBA_CMD         "casa/interior/bomba/cmd"
#define TOPICO_INTERIOR_BOMBA_ESTADO      "casa/interior/bomba/estado"
#define TOPICO_INTERIOR_BOMBA_OVERRIDE    "casa/interior/bomba/override"

// Sensores
#define TOPICO_SENSOR_TEMP                "casa/interior/sensor/temp"
#define TOPICO_SENSOR_HUM_AMB             "casa/interior/sensor/hum_amb"
#define TOPICO_SENSOR_HUM_SUELO           "casa/interior/sensor/hum_suelo"

// Inteligencia artificial
#define TOPICO_IA_PRESENCIA               "casa/ia/presencia"
#define TOPICO_IA_PROB_LLUVIA             "casa/ia/prob_lluvia"

// Garaje
#define TOPICO_GARAJE_MODO_CMD            "casa/garaje/modo/cmd"
#define TOPICO_GARAJE_MODO_ESTADO         "casa/garaje/modo/estado"
#define TOPICO_GARAJE_PORTON_CMD          "casa/garaje/porton/cmd"
#define TOPICO_GARAJE_PORTON_ESTADO       "casa/garaje/porton/estado"
#define TOPICO_GARAJE_ALARMA_CMD          "casa/garaje/alarma/cmd"
#define TOPICO_GARAJE_ALARMA_ESTADO       "casa/garaje/alarma/estado"

// Configuracion interior - contrato nuevo
#define TOPICO_CONFIG_INTERIOR_TEMP_MIN_CMD          "casa/config/interior/temp_min/cmd"
#define TOPICO_CONFIG_INTERIOR_TEMP_MAX_CMD          "casa/config/interior/temp_max/cmd"
#define TOPICO_CONFIG_INTERIOR_HUM_AMB_MIN_CMD       "casa/config/interior/hum_amb_min/cmd"
#define TOPICO_CONFIG_INTERIOR_HUM_AMB_MAX_CMD       "casa/config/interior/hum_amb_max/cmd"
#define TOPICO_CONFIG_INTERIOR_HUM_SUELO_MIN_CMD     "casa/config/interior/hum_suelo_min/cmd"
#define TOPICO_CONFIG_INTERIOR_HUM_SUELO_MAX_CMD     "casa/config/interior/hum_suelo_max/cmd"
#define TOPICO_CONFIG_INTERIOR_BOMBA_UMBRAL_CMD      "casa/config/interior/bomba_umbral/cmd"
#define TOPICO_CONFIG_INTERIOR_RESET_CMD             "casa/config/interior/reset/cmd"

#define TOPICO_CONFIG_INTERIOR_TEMP_MIN_ESTADO       "casa/config/interior/temp_min/estado"
#define TOPICO_CONFIG_INTERIOR_TEMP_MAX_ESTADO       "casa/config/interior/temp_max/estado"
#define TOPICO_CONFIG_INTERIOR_HUM_AMB_MIN_ESTADO    "casa/config/interior/hum_amb_min/estado"
#define TOPICO_CONFIG_INTERIOR_HUM_AMB_MAX_ESTADO    "casa/config/interior/hum_amb_max/estado"
#define TOPICO_CONFIG_INTERIOR_HUM_SUELO_MIN_ESTADO  "casa/config/interior/hum_suelo_min/estado"
#define TOPICO_CONFIG_INTERIOR_HUM_SUELO_MAX_ESTADO  "casa/config/interior/hum_suelo_max/estado"
#define TOPICO_CONFIG_INTERIOR_BOMBA_UMBRAL_ESTADO   "casa/config/interior/bomba_umbral/estado"

// Configuracion interior - topicos anteriores para compatibilidad
#define TOPICO_CONFIG_TEMP_MIN_CMD          "casa/interior/config/temp_min/cmd"
#define TOPICO_CONFIG_TEMP_MAX_CMD          "casa/interior/config/temp_max/cmd"
#define TOPICO_CONFIG_HUM_AMB_MIN_CMD       "casa/interior/config/hum_amb_min/cmd"
#define TOPICO_CONFIG_HUM_AMB_MAX_CMD       "casa/interior/config/hum_amb_max/cmd"
#define TOPICO_CONFIG_HUM_SUELO_MIN_CMD     "casa/interior/config/hum_suelo_min/cmd"
#define TOPICO_CONFIG_HUM_SUELO_MAX_CMD     "casa/interior/config/hum_suelo_max/cmd"
#define TOPICO_CONFIG_BOMBA_UMBRAL_CMD      "casa/interior/config/bomba_umbral/cmd"

#define TOPICO_CONFIG_TEMP_MIN_ESTADO       "casa/interior/config/temp_min/estado"
#define TOPICO_CONFIG_TEMP_MAX_ESTADO       "casa/interior/config/temp_max/estado"
#define TOPICO_CONFIG_HUM_AMB_MIN_ESTADO    "casa/interior/config/hum_amb_min/estado"
#define TOPICO_CONFIG_HUM_AMB_MAX_ESTADO    "casa/interior/config/hum_amb_max/estado"
#define TOPICO_CONFIG_HUM_SUELO_MIN_ESTADO  "casa/interior/config/hum_suelo_min/estado"
#define TOPICO_CONFIG_HUM_SUELO_MAX_ESTADO  "casa/interior/config/hum_suelo_max/estado"
#define TOPICO_CONFIG_BOMBA_UMBRAL_ESTADO   "casa/interior/config/bomba_umbral/estado"

// Entradas fisicas
#define TOPICO_ENTRADA_BTN_FOCO          "casa/fisico/btn_foco/estado"
#define TOPICO_ENTRADA_BTN_VENT          "casa/fisico/btn_vent/estado"
#define TOPICO_ENTRADA_BTN_BOMBA         "casa/fisico/btn_bomba/estado"
#define TOPICO_ENTRADA_BTN_ABRIR         "casa/fisico/btn_abrir/estado"
#define TOPICO_ENTRADA_BTN_CERRAR        "casa/fisico/btn_cerrar/estado"
#define TOPICO_ENTRADA_BTN_STOP_MOTOR    "casa/fisico/btn_stop_motor/estado"
#define TOPICO_ENTRADA_BTN_STOP          "casa/fisico/btn_stop/estado"
#define TOPICO_ENTRADA_FC_ABIERTO        "casa/fisico/fc_abierto/estado"
#define TOPICO_ENTRADA_FC_CERRADO        "casa/fisico/fc_cerrado/estado"
#define TOPICO_FISICO_FOCO_ACCION        "casa/fisico/foco/accion"
#define TOPICO_FISICO_VENT_ACCION        "casa/fisico/vent/accion"

#define TOPICO_FOCO_ZC_CONTADOR          "casa/foco/zc/contador"
#define TOPICO_FOCO_ZC_FREQ              "casa/foco/zc/freq"

// Pines principales
#define PIN_FOCO_ZC        GPIO_NUM_27
#define PIN_FOCO_TRIAC     GPIO_NUM_26
#define BTN_FOCO           GPIO_NUM_14

#define PIN_VENTILADOR     GPIO_NUM_19
#define BTN_VENT           GPIO_NUM_21

#define PIN_BOMBA          GPIO_NUM_23
#define BTN_BOMBA          GPIO_NUM_22

#define SOIL_PIN           GPIO_NUM_32
#define DHT_PIN            GPIO_NUM_4

#define PIN_MOTOR_PWM      GPIO_NUM_16
#define PIN_MOTOR_IN1      GPIO_NUM_18
#define PIN_MOTOR_IN2      GPIO_NUM_17
#define PIN_ALARMA_VISUAL  GPIO_NUM_13

#define BTN_ABRIR          GPIO_NUM_33
#define BTN_CERRAR         GPIO_NUM_25
#define FC_ABIERTO         GPIO_NUM_36
#define FC_CERRADO         GPIO_NUM_39
#define BTN_STOP_MOTOR     GPIO_NUM_34
#define BTN_STOP           GPIO_NUM_35

// PWM ventilador
#define PWM_VENT_CANAL     LEDC_CHANNEL_0
#define PWM_VENT_TIMER     LEDC_TIMER_0
#define PWM_VENT_MODO      LEDC_LOW_SPEED_MODE
#define PWM_VENT_FREQ_HZ   5000
#define PWM_VENT_RES       LEDC_TIMER_10_BIT
#define PWM_DUTY_MAX       1023

// PWM motor porton
#define PWM_MOTOR_CANAL    LEDC_CHANNEL_1
#define PWM_MOTOR_TIMER    LEDC_TIMER_1
#define PWM_MOTOR_MODO     LEDC_LOW_SPEED_MODE
#define PWM_MOTOR_FREQ_HZ  5000
#define PWM_MOTOR_RES      LEDC_TIMER_10_BIT

#define HABILITAR_PRUEBA_FOCO_TRIAC 1
#define USAR_SENSORES_SIMULADOS     0
#define ALARMA_VISUAL_LOGICA_INVERTIDA 1

#define FC28_ADC_SECO     4000
#define FC28_ADC_MOJADO   2700

#define TEMP_SIM_INICIAL        24.5f
#define HUM_AMB_SIM_INICIAL     62.0f
#define HUM_SUELO_SIM_INICIAL   45

// Valores por defecto de usuario
#define CONFIG_TEMP_MIN_DEFECTO             24
#define CONFIG_TEMP_MAX_DEFECTO             30
#define CONFIG_HUM_AMB_MIN_DEFECTO          50
#define CONFIG_HUM_AMB_MAX_DEFECTO          75
#define CONFIG_HUM_SUELO_MIN_DEFECTO        35
#define CONFIG_HUM_SUELO_MAX_DEFECTO        55
#define CONFIG_BOMBA_UMBRAL_DEFECTO         35

// Control fisico avanzado
#define TIEMPO_PULSACION_LARGA_MS           700
#define INTERVALO_AJUSTE_FISICO_MS          250
#define PASO_DIMMER_FISICO                  5
#define PASO_PWM_FISICO                     5

#endif
