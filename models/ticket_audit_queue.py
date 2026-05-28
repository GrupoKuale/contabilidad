import json
import logging
from odoo import models, fields, api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


class TicketAuditQueue(models.Model):
    _name = 'contabilidad_kuale.ticket_audit_queue'
    _description = 'Cola de Auditoría de Tickets'
    _order = 'create_date asc'
    _rec_name = 'job_uuid'

    job_uuid = fields.Char('UUID del Job', index=True, readonly=True, copy=False)
    company_id = fields.Many2one('res.company', string='Empresa', readonly=True)
    branch_id = fields.Many2one('res.company', string='Sucursal', readonly=True)
    payload = fields.Text('Payload JSON', readonly=True)
    ticket_count = fields.Integer('Tickets en el lote', readonly=True)
    final_audit = fields.Boolean('Auditoría final', readonly=True)

    status = fields.Selection([
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('done', 'Completado'),
        ('error', 'Error'),
    ], string='Estado', default='pending', index=True, readonly=True)

    result_summary = fields.Text('Detalle de errores', readonly=True)
    error_count = fields.Integer('Tickets con error', readonly=True)
    success_count = fields.Integer('Tickets exitosos', readonly=True)
    processed_at = fields.Datetime('Procesado en', readonly=True)
    create_date = fields.Datetime('Recibido en', readonly=True)

    def _process_pending_jobs(self):
        pending_ids = self.sudo().search(
            [('status', '=', 'pending')], limit=1, order='create_date asc'
        ).ids

        for job_id in pending_ids:
            with self.pool.cursor() as cr:
                env_temp = api.Environment(cr, SUPERUSER_ID, {})
                admin_id = env_temp.ref('base.user_admin').id
                
                env = api.Environment(cr, admin_id, {})
                
                job = env[self._name].browse(job_id)

                company_ids = []
                if job.branch_id:
                    company_ids.append(job.branch_id.id)
                if job.company_id:
                    company_ids.append(job.company_id.id)

                
                if company_ids:
                    job = job.with_company(company_ids[0]).with_context(allowed_company_ids=company_ids)

                job.write({'status': 'processing'})
                env.cr.commit()

                try:
                    result = job._run()
                    
                    # Si el job no terminó todos los tickets, guardamos progreso y lo regresamos a pendiente
                    if result.get('status') == 'partial':
                        job.write({
                            'status': 'pending',
                            'success_count': job.success_count + result.get('success', 0),
                            'error_count': job.error_count + result.get('errors', 0),
                        })
                        env.cr.commit()
                        continue

                    # Si terminó por completo, recuperamos los errores acumulados (si los hay)
                    existing_errors = []
                    if job.result_summary:
                        try:
                            existing_errors = json.loads(job.result_summary)
                        except:
                            pass
                    
                    all_errors = existing_errors + result.get('error_details', [])

                    job.write({
                        'status': 'done',
                        'processed_at': fields.Datetime.now(),
                        'success_count': job.success_count + result.get('success', 0),
                        'error_count': job.error_count + result.get('errors', 0),
                        'result_summary': json.dumps(all_errors, ensure_ascii=False)[:10000],
                    })
                    env.cr.commit()

                except Exception as e:
                    # Capturar job_uuid ANTES de intentar acceder a la BD
                    # (el cursor puede estar cerrado si el cron fue interrumpido)
                    try:
                        job_uuid_str = job.job_uuid
                    except Exception:
                        job_uuid_str = str(job_id)
                    _logger.exception("Error crítico procesando job %s", job_uuid_str)
                    try:
                        env.cr.rollback()
                    except Exception:
                        pass
                    try:
                        job.write({
                            'status': 'error',
                            'processed_at': fields.Datetime.now(),
                            'result_summary': str(e)[:2000],
                        })
                        env.cr.commit()
                    except Exception:
                        _logger.error("No se pudo actualizar el estado del job %s tras el error.", job_uuid_str)

    def _run(self):
        from odoo.addons.contabilidad_kuale.controllers.ticket_monitor import _process_audit_batch
        payload = json.loads(self.payload)
        tickets = payload.get('tickets', [])
        
        CHUNK_SIZE = 150 
        tickets_to_process = tickets[:CHUNK_SIZE]
        remaining_tickets = tickets[CHUNK_SIZE:]

      
        company_ids = []
        if self.branch_id:
            company_ids.append(self.branch_id.id)
        if self.company_id:
            company_ids.append(self.company_id.id)

        audit_env = self.sudo().with_context(allowed_company_ids=company_ids).env

        result = _process_audit_batch(
            audit_env,
            tickets_to_process,
            self.company_id,
            self.branch_id,
            self.final_audit
        )

        if remaining_tickets:
            payload['tickets'] = remaining_tickets
            
            existing_errors = []
            if self.result_summary:
                try:
                    existing_errors = json.loads(self.result_summary)
                except:
                    pass
            
            new_errors = existing_errors + result.get('error_details', [])

            self.write({
                'payload': json.dumps(payload, ensure_ascii=False),
                'ticket_count': len(remaining_tickets),
                'result_summary': json.dumps(new_errors, ensure_ascii=False)[:10000]
            })
            
            return {
                'status': 'partial',
                'success': result.get('success', 0),
                'errors': result.get('errors', 0)
            }
        else:
            return {
                'status': 'done',
                'success': result.get('success', 0),
                'errors': result.get('errors', 0),
                'error_details': result.get('error_details', [])
            }

    def action_retry(self):
        """Permite reintentar un job en estado error desde la UI."""
        for rec in self:
            if rec.status == 'error':
                rec.write({
                    'status': 'pending',
                    'result_summary': False,
                    'error_count': 0,
                    'success_count': 0,
                    'processed_at': False,
                })
