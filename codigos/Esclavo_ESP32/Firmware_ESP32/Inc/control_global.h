#ifndef CONTROL_GLOBAL_H
#define CONTROL_GLOBAL_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    MODO_MANUAL = 0,
    MODO_AUTO,
    MODO_SMART
} modo_sistema_t;

typedef struct {
    uint8_t nivel_foco;
    bool bomba_encendida;
    uint8_t velocidad_ventilador;

    bool foco_override;
    bool bomba_override;
    bool ventilador_override;

    float temperatura;
    float humedad_ambiente;
    uint8_t humedad_suelo;

    bool presencia;
    float probabilidad_lluvia;

    bool paro_emergencia;
    bool wifi_conectado;
    bool mqtt_conectado;
    bool estado_seguro_arranque;

    uint32_t contador_fallas;
    char ultima_falla[48];

    modo_sistema_t modo_actual;
} estado_sistema_t;

void control_global_iniciar(void);
bool control_global_procesar_mensaje(const char *topico, const char *mensaje);

void control_global_actualizar_sensores(float temperatura, float humedad_ambiente, uint8_t humedad_suelo);

void control_global_set_nivel_foco(uint8_t nivel, bool activar_override);
void control_global_set_bomba(bool encender, bool activar_override);
void control_global_set_ventilador(uint8_t velocidad, bool activar_override);

void control_global_cargar_nvs(void);
void control_global_guardar_nvs(void);
void control_global_registrar_falla(const char *codigo);

estado_sistema_t control_global_obtener_estado(void);

void control_global_set_wifi(bool conectado);
void control_global_set_mqtt(bool conectado);

const char *control_global_modo_texto(modo_sistema_t modo);

void control_global_toggle_foco_fisico(void);
void control_global_toggle_bomba_fisico(void);
void control_global_toggle_ventilador_fisico(void);
void control_global_ajustar_foco_fisico(int8_t delta);
void control_global_ajustar_ventilador_fisico(int8_t delta);

#endif
