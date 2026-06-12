#ifndef CONFIG_USUARIO_H
#define CONFIG_USUARIO_H

#include <stdint.h>
#include <stdbool.h>

typedef struct {
    uint8_t temp_min;
    uint8_t temp_max;
    uint8_t hum_amb_min;
    uint8_t hum_amb_max;
    uint8_t hum_suelo_min;
    uint8_t hum_suelo_max;
    uint8_t bomba_umbral_auto;
} config_usuario_t;

void config_usuario_iniciar(void);
bool config_usuario_procesar_mensaje(const char *topico, const char *mensaje);
void config_usuario_restaurar_defecto(void);

config_usuario_t config_usuario_obtener(void);

#endif
