#include "bsp_servo.h"

#if USE_SERVO

/* --- Handles des timers locaux --- */
static TIM_HandleTypeDef htim1;
static TIM_HandleTypeDef htim2;
static TIM_HandleTypeDef htim3;

/* --- Structure d'un servo --- */
typedef struct {
    TIM_HandleTypeDef *htim;
    uint32_t           channel;
    uint16_t           pulse_min;
    uint16_t           pulse_max;
    float              angle_range;   /* portee angulaire totale (deg) */
} servo_cfg_t;

/* --- Table des 5 servos (pointeurs remplis dans BSP_SERVO_init) ---
 * Plage prudente : 700 us = 0 deg, 2300 us = 180 deg
 * -> compatible SG90, MG90S, MG996R, DS3225 sans risque.
 *    Si tu veux gagner quelques degres en plus, descends pulse_min
 *    a 600 et monte pulse_max a 2400 progressivement, en verifiant
 *    que le servo ne force pas en butee.
 *
 *  Mapping pins :
 *    SERVO_1 -> PA8  (TIM1_CH1, AF6)
 *    SERVO_2 -> PA9  (TIM1_CH2, AF6)
 *    SERVO_3 -> PA10 (TIM1_CH3, AF6)   <-- nouveau
 *    SERVO_4 -> PA1  (TIM2_CH2, AF1)   -- inutilise
 *    SERVO_5 -> PA6  (TIM3_CH1, AF2)   -- inutilise
 */
static servo_cfg_t servo_table[SERVO_COUNT] = {
    { NULL, TIM_CHANNEL_1,  700, 2300, 180.0f }, /* SERVO_1 → PA8  (180°)            */
    { NULL, TIM_CHANNEL_2,  500, 2500, 360.0f }, /* SERVO_2 → PA9  carrousel 360°    */
    { NULL, TIM_CHANNEL_3,  700, 2300, 180.0f }, /* SERVO_3 → PA10 trappe (180°)     */
    { NULL, TIM_CHANNEL_2, 1000, 2000, 180.0f }, /* SERVO_4 → PA1                    */
    { NULL, TIM_CHANNEL_1, 1000, 2000, 180.0f }, /* SERVO_5 → PA6                    */
};

/* ----------------------------------------------------------------
 * Configure un timer en PWM 50 Hz
 * Sysclock = 72 MHz
 * Prescaler = 71  → timer clock = 72MHz / 72 = 1 MHz
 * Period    = 19999 → 1MHz / 20000 = 50 Hz
 * Pulse CCR en µs directement (1000 = 1ms = 0°, 2000 = 2ms = 180°)
 * ---------------------------------------------------------------- */
static void timer_pwm_init(TIM_HandleTypeDef *htim, TIM_TypeDef *instance)
{
    TIM_OC_InitTypeDef sConfigOC = {0};

    htim->Instance               = instance;
    htim->Init.Prescaler         = 71;
    htim->Init.CounterMode       = TIM_COUNTERMODE_UP;
    htim->Init.Period            = 19999;
    htim->Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
    htim->Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    HAL_TIM_PWM_Init(htim);

    sConfigOC.OCMode     = TIM_OCMODE_PWM1;
    sConfigOC.Pulse      = 1500;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;

    HAL_TIM_PWM_ConfigChannel(htim, &sConfigOC, TIM_CHANNEL_1);
    HAL_TIM_PWM_ConfigChannel(htim, &sConfigOC, TIM_CHANNEL_2);
    HAL_TIM_PWM_ConfigChannel(htim, &sConfigOC, TIM_CHANNEL_3);
}

/* ---------------------------------------------------------------- */
void BSP_SERVO_init(void)
{
    /* Lie les handles aux entrées de la table */
    servo_table[SERVO_1].htim = &htim1;
    servo_table[SERVO_2].htim = &htim1;
    servo_table[SERVO_3].htim = &htim1;   /* PA10 = TIM1_CH3 */
    servo_table[SERVO_4].htim = &htim2;
    servo_table[SERVO_5].htim = &htim3;

    /* Active les horloges timers */
    __HAL_RCC_TIM1_CLK_ENABLE();
    __HAL_RCC_TIM2_CLK_ENABLE();
    __HAL_RCC_TIM3_CLK_ENABLE();

    /* Active l'horloge GPIOA */
    __HAL_RCC_GPIOA_CLK_ENABLE();

    /* Configure les pins PWM */
    GPIO_InitTypeDef gpio = {0};
    gpio.Mode  = GPIO_MODE_AF_PP;
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;

    /* PA8 = TIM1_CH1 (SERVO_1)
     * PA9 = TIM1_CH2 (SERVO_2)
     * PA10 = TIM1_CH3 (SERVO_3) */
    gpio.Pin       = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10;
    gpio.Alternate = GPIO_AF6_TIM1;
    HAL_GPIO_Init(GPIOA, &gpio);

    /* PA0 = TIM2_CH1 (SERVO_3), PA1 = TIM2_CH2 (SERVO_4) */
    gpio.Pin       = GPIO_PIN_0 | GPIO_PIN_1;
    gpio.Alternate = GPIO_AF1_TIM2;
    HAL_GPIO_Init(GPIOA, &gpio);

    /* PA6 = TIM3_CH1 (SERVO_5) */
    gpio.Pin       = GPIO_PIN_6;
    gpio.Alternate = GPIO_AF2_TIM3;
    HAL_GPIO_Init(GPIOA, &gpio);

    /* Initialise les 3 timers */
    timer_pwm_init(&htim1, TIM1);
    timer_pwm_init(&htim2, TIM2);
    timer_pwm_init(&htim3, TIM3);

    /* Démarre le PWM sur tous les canaux */
    for (int i = 0; i < SERVO_COUNT; i++) {
        HAL_TIM_PWM_Start(servo_table[i].htim, servo_table[i].channel);
    }

    /* Position neutre au démarrage (90° = centre 0..180°) */
    for (int i = 0; i < SERVO_COUNT; i++) {
        BSP_SERVO_set_angle((servo_id_t)i, 90.0f);
    }
}

/* ----------------------------------------------------------------
 * Convertit un angle en largeur d'impulsion (µs), selon la portee
 * propre a chaque servo (angle_range) :
 *   angle 0           -> pulse_min
 *   angle/2           -> centre
 *   angle_range       -> pulse_max
 * Ex. SERVO_2 (carrousel 360°) : 500 µs = 0°, 2500 µs = 360°.
 * ---------------------------------------------------------------- */
void BSP_SERVO_set_angle(servo_id_t id, float angle)
{
    if (id >= SERVO_COUNT) return;

    servo_cfg_t *s = &servo_table[id];

    if (angle < 0.0f)              angle = 0.0f;
    if (angle > s->angle_range)    angle = s->angle_range;

    uint16_t pulse = (uint16_t)(s->pulse_min
                     + (angle / s->angle_range)
                     * (s->pulse_max - s->pulse_min));

    __HAL_TIM_SET_COMPARE(s->htim, s->channel, pulse);
}

#endif /* USE_SERVO */
