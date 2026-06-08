#ifndef BSP_SERVO_H
#define BSP_SERVO_H

#include "stm32g4xx_hal.h"
#include "config.h"

#if USE_SERVO

/* Identifiants des 5 servos */
typedef enum {
    SERVO_1,
    SERVO_2,
    SERVO_3,
    SERVO_4,
    SERVO_5,
    SERVO_COUNT
} servo_id_t;

/* Initialise tous les timers PWM pour les servos */
void BSP_SERVO_init(void);

/* Déplace un servo vers un angle de 0 à 180 degrés */
void BSP_SERVO_set_angle(servo_id_t id, float angle);

#endif /* USE_SERVO */
#endif /* BSP_SERVO_H */
