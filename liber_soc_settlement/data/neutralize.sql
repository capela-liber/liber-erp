-- Uma base neutralizada (dev, staging, uma cópia para ensaio) não manda mapa
-- para cliente nenhum. O `odoo neutralize` já desliga TODOS os crons, então
-- esta linha é o cinto e suspensório do caso em que alguém reativa os crons da
-- consignação para ensaiar a rotina: o interruptor do agendamento fica
-- desligado, e o mapa mensal continua sem sair sozinho.
UPDATE ir_config_parameter
   SET value = 'False'
 WHERE key = 'soc_settlement.map_schedule_enabled';
