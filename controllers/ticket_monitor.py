import json
import logging
import uuid as uuid_lib
from odoo import http, SUPERUSER_ID
from odoo.http import request
from datetime import datetime
from pytz import timezone, utc

_logger = logging.getLogger(__name__)


# TODO!= METER LO DE DESCUENTOS AL TICKET Y AL TICKET AUDIT

class TicketCreationError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def _to_utc(datetime_str, tz_name='America/Mexico_City'):
    if not datetime_str:
        return False
    local = timezone(tz_name)
    local_dt = local.localize(datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S"), is_dst=None)
    utc_dt = local_dt.astimezone(utc)
    return utc_dt.replace(tzinfo=None)


def _get_company(company_id):
    return request.env['res.company'].sudo().search([
        ('company_clave', '=', company_id)
    ], limit=1)


def _get_system_ticket(ticket_folio, company_id, branch_id):
    return request.env['contabilidad_kuale.ticket_monitor'].sudo().search([
        ('ticket_folio', '=', ticket_folio),
        ('company_id', '=', company_id),
        ('branch_id', '=', branch_id)
    ], limit=1)


def _get_payment_type(payment_clave):
    return request.env['cfdi.claveformadepago'].sudo().search([
        ('third_party_id', '=', payment_clave)
    ], limit=1)


def _get_payment_method(payment_method):
    return request.env['cfdi.clavemetododepago'].sudo().search([
        ('Clave_metodo_de_pago', '=', payment_method)
    ], limit=1)


def _get_sell_type(sell_type):
    return request.env['contabilidad_kuale.ticket_sell_types'].sudo().search([
        ('clave', '=', sell_type), ], limit=1)


def _get_discount(clave):
    return request.env['contabilidad_kuale.ticket_discount'].sudo().search([
        ('clave', '=', clave), ], limit=1)


def _get_company_env(env, company_id):
    return env['res.company'].sudo().search(
        [('company_clave', '=', company_id)], limit=1
    )

def _get_payment_type_env(env, payment_clave):
    return env['cfdi.claveformadepago'].sudo().search(
        [('third_party_id', '=', payment_clave)], limit=1
    )

def _get_employee_env(env, employee_code):
    if not employee_code:
        return None
    return env['hr.employee'].sudo().search(
        [('cashier_code', '=', employee_code)], limit=1
    )

def _get_discount_env(env, clave):
    return env['contabilidad_kuale.ticket_discount'].sudo().search(
        [('clave', '=', clave)], limit=1
    )

def _get_discount_ids(discount_ids):
    discounts = []
    for discount_clave in discount_ids:
        discount = _get_discount(discount_clave)
        if discount:
            discounts.append(discount.id)
        else:
            raise TicketCreationError(400, f"No se encontro descuentos con la clave: {discount_clave}")
    return discounts


def _get_payments(payments_raw):
    payment_lines = []
    for pay in payments_raw:
        payment_type = _get_payment_type(pay.get('payment_type'))
        if not payment_type:
            raise TicketCreationError(417, f"No se encontró forma de pago con clave: {pay.get('payment_type')}")

        amount = pay.get('amount')
        if amount is None:
            raise TicketCreationError(417, "Cada método de pago debe incluir un monto")

        payment_lines.append((0, 0, {
            'payment_type': payment_type.id,
            'amount': amount,
        }))
    return payment_lines


def _create_ticket(ticket):
    company = _get_company(ticket.get('company_id'))
    branch = _get_company(ticket.get('branch_id'))
    system_ticket = _get_system_ticket(ticket.get('ticket_folio'), company.id, branch.id)
    if system_ticket:
        raise TicketCreationError(417, "Ya hay un ticket registrado con este folio para esta empresa")

    errors = []

    sell_type = _get_sell_type(ticket.get('sell_type'))
    if not sell_type:
        errors.append(f"Tipo de venta (Clave: {ticket.get('sell_type')})")

    cashier = None
    closing_cashier = None
    if ticket.get('sell_type') != '1004':
        cashier = _get_employee(ticket.get('cashier'))
        if not cashier:
            errors.append(f"Cajero (Clave: {ticket.get('cashier')})")

        closing_cashier = _get_employee(ticket.get('closing_cashier'))
        if not closing_cashier:
            errors.append(f"Cajero de cierre (Clave: {ticket.get('closing_cashier')})")

    payment_type = _get_payment_type(ticket.get('payment_type'))
    if not payment_type:
        errors.append(f"Forma de pago principal (Clave: {ticket.get('payment_type')})")

    payment_method = _get_payment_method(ticket.get('payment_method'))
    if not payment_method:
        errors.append(f"Método de pago (Clave: {ticket.get('payment_method')})")

    authorized_employee = None
    if ticket.get('discount_ids') and ticket.get('discount_authorized'):
        authorized_employee = _get_employee(ticket.get('discount_authorized'))
        if not authorized_employee:
            errors.append(f"Autorizador de descuento (Clave: {ticket.get('discount_authorized')})")

    void_authorized = None
    if ticket.get('void_authorized'):
        void_authorized = _get_employee(ticket.get('void_authorized'))
        if not void_authorized:
            errors.append(f"Autorizador de cancelación (Clave: {ticket.get('void_authorized')})")

    # Validar descuentos
    discount_ids_raw = ticket.get('discount_ids', [])
    valid_discount_ids = []
    for d_clave in discount_ids_raw:
        discount = _get_discount(d_clave)
        if discount:
            valid_discount_ids.append(discount.id)
        else:
            errors.append(f"Descuento (Clave: {d_clave})")
    
    discount_ids = [(6, 0, valid_discount_ids)] if discount_ids_raw else [(6, 0, [])]

    # Validar pagos adicionales
    payments_raw = ticket.get('payments', [])
    payment_lines = []
    for pay in payments_raw:
        paytype = _get_payment_type(pay.get('payment_type'))
        if not paytype:
            errors.append(f"Forma de pago en cobro múltiple (Clave: {pay.get('payment_type')})")
        else:
            amt = pay.get('amount')
            if amt is None:
                errors.append(f"Cobro sin monto (Clave forma de pago: {pay.get('payment_type')})")
            else:
                payment_lines.append((0, 0, {'payment_type': paytype.id, 'amount': amt}))

    # Validar productos y calcular subtotal esperado
    incoming_third_party_ids = [prod.get('third_party_id') for prod in ticket.get('products', []) if prod.get('third_party_id')]
    found_products = request.env['product.template'].sudo().search([('third_party_id', 'in', incoming_third_party_ids)])
    found_third_party_ids = found_products.mapped('third_party_id')

    product_lines = []
    expected_subtotal = 0.0
    for prod in ticket.get('products', []):
        third_party_id = prod.get('third_party_id')
        qty = float(prod.get('quantity') or 0)
        u_price = float(prod.get('unit_price') or 0)
        
        # Calcular subtotal esperado usando los precios unitarios enviados en el JSON
        expected_subtotal += qty * u_price

        if not third_party_id:
            errors.append("Producto sin código (third_party_id ausente)")
        elif third_party_id not in found_third_party_ids:
            errors.append(f"Producto (Código: {third_party_id}) no encontrado en el catálogo de Odoo")

        product_lines.append((0, 0, {
            'third_party_id': third_party_id,
            'quantity': qty,
            'unit_price': u_price,
            'discount': float(prod.get('discount') or 0),
        }))

    incoming_subtotal = float(ticket.get('subtotal') or 0.0)
    ticket_discount = float(ticket.get('discount') or 0.0)
    expected_net_subtotal = expected_subtotal - ticket_discount

    # Tolerancia de 0.02 centavos
    if not errors and abs(expected_net_subtotal - incoming_subtotal) > 0.02:
        errors.append(
            f"El subtotal enviado ({incoming_subtotal}) no coincide con la suma de los productos menos el descuento ({expected_net_subtotal:.2f}). "
            f"Folio: {ticket.get('ticket_folio')}"
        )

    # Agrupación y notificación si hay errores
    if errors:
        folio = ticket.get('ticket_folio', 'N/A')
        sucursal_name = branch.name if branch else 'N/A'
        empresa_name = company.name if company else 'N/A'

        error_list_html = "<br/>".join([f"- {err}" for err in errors])
        error_context_html = f"<b>Empresa:</b> {empresa_name}<br/><b>Sucursal:</b> {sucursal_name}<br/><b>Folio de Ticket:</b> {folio}<br/><br/><b>Elementos faltantes/inválidos en el catálogo de Odoo:</b><br/>{error_list_html}"

        template = company.missing_product_email_template_id
        if template:
            try:
                rendered_body = template.sudo()._render_field('body_html', [company.id])[company.id]
                final_body = str(rendered_body).replace('__PRODUCTOS_FALTANTES__', error_context_html)
                template.sudo().send_mail(
                    company.id, 
                    force_send=True,
                    email_values={'body_html': final_body}
                )
            except Exception as e:
                print(f"Error al enviar correo de validaciones: {e}")

        channel = company.ticket_error_channel_id
        if channel:
            message_text = "\n".join([f"- {err}" for err in errors])
            message_chat = f"🛑 Fallo al subir ticket API (Folio: {folio} | Sucursal: {sucursal_name} | Empresa: {empresa_name}). Faltan registrar los siguientes elementos:\n{message_text}"
            try:
                odoobot = request.env.ref('base.partner_root')
                channel.sudo().message_post(
                    body=message_chat, 
                    author_id=odoobot.id,
                    message_type='comment', 
                    subtype_xmlid='mail.mt_comment'
                )
            except Exception as e:
                print(f"Error al enviar mensaje a Discuss: {e}")

        raise TicketCreationError(400, f"No se puede subir el ticket. Faltan registrar los siguientes elementos: {', '.join(errors)}")

    # Identificar si el ticket está vacío (total 0 y sin productos)
    is_empty_ticket = False
    if float(ticket.get('total') or 0.0) == 0.0 and not ticket.get('products'):
        is_empty_ticket = True

    request.env['contabilidad_kuale.ticket_monitor'].sudo().create({
        'company_id': company.id,
        'branch_id': branch.id,
        'ticket_folio': ticket.get('ticket_folio'),
        'folio': ticket.get('folio'),
        'date': _to_utc(ticket.get('date')),
        'closed_date': _to_utc(ticket.get('end_date')) if ticket.get('end_date') else None,
        'cashier': cashier.id if cashier else None,
        'closing_cashier': closing_cashier.id if closing_cashier else None,
        'payment_method': payment_method.id,
        'payment_type': payment_type.id,
        'iva': ticket.get('iva'),
        'total': ticket.get('total'),
        'subtotal': ticket.get('subtotal') if ticket.get('subtotal') else 0.0,
        'discount_ids': discount_ids,
        'discount': ticket.get('discount'),
        'discount_authorized': authorized_employee.id if authorized_employee else None,
        'void_authorized': void_authorized.id if void_authorized else None,
        'reprint_number': ticket.get('reprint_number'),
        'modification_status': False,
        'is_empty_ticket': is_empty_ticket,
        'sell_type': sell_type.id,
        'product_line': product_lines,
        'payments_ids': payment_lines,
    })
    print('ticket creado satisfactoriamente')

    return True


def _create_ticket_audit(ticket, audit_status):
    company = _get_company(ticket.get('company_id'))
    branch = _get_company(ticket.get('branch_id'))
    payment_type = _get_payment_type(ticket.get('payment_type'))
    payment_method = _get_payment_method(ticket.get('payment_method'))
    
    closing_cashier = None
    if ticket.get('sell_type') != '1004':
        closing_cashier = _get_employee(ticket.get('closing_cashier'))
        if not closing_cashier:
            raise TicketCreationError(400,
                                      f"No se encontró ningun empleado con el codigo de cajero {ticket.get('closing_cashier')} ")

    audit = request.env['contabilidad_kuale.ticket_monitor_audit'].sudo().search([
        ('ticket_folio', '=', ticket.get('ticket_folio')),
        ('company_id', '=', company.id),
        ('branch_id', '=', branch.id)
    ], limit=1)

    product_line = [(0, 0, {
        'third_party_id': prod.get('third_party_id'),
        'quantity': float(prod.get('quantity') or 0.0),
        'unit_price': float(prod.get('unit_price') or 0.0),
        'discount': float(prod.get('discount') or 0.0),
    }) for prod in ticket.get('products', [])]

    discount_ids_raw = ticket.get('discount_ids', [])
    discount_ids = [(6, 0, _get_discount_ids(discount_ids_raw))] if discount_ids_raw else [(6, 0, [])]

    incoming_auth = None
    if ticket.get('discount_authorized'):
        incoming_auth = _get_employee(ticket.get('discount_authorized'))

    payments_raw = ticket.get('payments', [])
    audit_payments = _get_payments(payments_raw)
    void_authorized = _get_employee(ticket.get('void_authorized'))

    values = {
        'company_id': company.id,
        'branch_id': branch.id,
        'ticket_folio': ticket.get('ticket_folio'),
        'closed_date': _to_utc(ticket.get('end_date')),
        'closing_cashier': closing_cashier.id if closing_cashier else None,
        'audit_payment_method': payment_method.id,
        'audit_payment_type': payment_type.id,
        'audit_iva': ticket.get('iva'),
        'audit_total': ticket.get('total'),
        'audit_subtotal': ticket.get('subtotal'),
        'audit_discount_ids': discount_ids,
        'audit_discount': ticket.get('discount'),
        'audit_discount_authorized': incoming_auth.id if incoming_auth else None,
        'audit_void_authorized': void_authorized.id if void_authorized else None,
        'audit_reprint_number': ticket.get('reprint_number'),
        'audit_status': audit_status,
        'audit_ticket_status': '0',
        'audit_product_line': [(5, 0, 0)] + product_line,
        'audit_payments_ids': [(5, 0, 0)] + audit_payments,
    }

    if audit:
        audit.write(values)
    else:
        request.env['contabilidad_kuale.ticket_monitor_audit'].sudo().create(values)


def _compare_product_lines(ticket_products, system_lines):
    def _as_float(value):
        try:
            return float(value or 0)
        except (ValueError, TypeError):
            return 0.0

    def _almost_equal(a, b, tol=1e-6):
        return abs(_as_float(a) - _as_float(b)) < tol

    system_products = {
        (line.third_party_id if line.third_party_id else None): line
        for line in system_lines
    }

    if len(ticket_products) != len(system_products):
        return True

    for prod in ticket_products:
        third_party_id = prod.get('third_party_id') if prod.get('third_party_id') else None
        system_product = system_products.get(third_party_id)

        if not system_product:
            return True

        if (
                not _almost_equal(prod.get('quantity'), system_product.quantity) or
                not _almost_equal(prod.get('unit_price'), system_product.unit_price) or
                not _almost_equal(prod.get('discount'), system_product.discount)
        ):
            return True

    return False


def _compare_ticket_meta(ticket, system_ticket):
    def _as_float(value):
        try:
            return float(value or 0)
        except (ValueError, TypeError):
            return 0.0

    def _almost_equal(a, b, tol=1e-6):
        return abs(_as_float(a) - _as_float(b)) < tol

    iva_diff = _as_float(ticket.get('iva')) != system_ticket.iva
    subtotal_diff = _as_float(ticket.get('subtotal')) != system_ticket.subtotal
    total_diff = _as_float(ticket.get('total')) != system_ticket.total
    discount_diff = _as_float(ticket.get('discount')) != system_ticket.discount

    payment_type_id = _get_payment_type(ticket.get('payment_type')).id
    payment_method_id = _get_payment_method(ticket.get('payment_method')).id

    payment_type_diff = payment_type_id != system_ticket.payment_type.id
    payment_method_diff = payment_method_id != system_ticket.payment_method.id

    incoming_discount_ids = set(_get_discount_ids(ticket.get('discount_ids', [])))
    system_discount_ids = set(system_ticket.discount_ids.ids)

    discount_diff_ids = (
            len(incoming_discount_ids) != len(system_discount_ids)
            or not incoming_discount_ids.issubset(system_discount_ids)
    )

    incoming_auth_code = ticket.get('discount_authorized')
    if incoming_auth_code:
        incoming_auth = _get_employee(incoming_auth_code)
        system_auth = system_ticket.discount_authorized

        auth_diff = (
                incoming_auth and
                incoming_auth.id != (system_auth.id if system_auth else None))
    else:
        auth_diff = False

    incoming_payments = ticket.get('payments', [])
    system_payments = system_ticket.payments_ids

    if len(incoming_payments) != len(system_payments):
        return True, 'pago'

    for pay in incoming_payments:
        pay_type = _get_payment_type(pay.get('payment_type'))
        amount = _as_float(pay.get('amount'))
        found = False

        for line in system_payments:
            if (
                    line.payment_type.id == pay_type.id
                    and _almost_equal(line.amount, amount)
            ):
                found = True
                break

        if not found:
            return True, 'pago'

    if iva_diff:
        return True, 'iva'
    if payment_type_diff or payment_method_diff:
        return True, 'pago'
    if auth_diff:
        return True, 'descuento'
    if total_diff or subtotal_diff or discount_diff or discount_diff_ids:
        return True, 'monto'

    return False, ''


def _get_employee(employee_code):
    if not employee_code:
        return None
    return request.env['hr.employee'].sudo().search([
        ('cashier_code', '=', employee_code),
    ], limit=1)


def _response(status: int, message: str, data: list | None = None):
    return request.make_json_response({
        'status': status,
        'message': message,
        'data': data or []
    }, status=status)


def _get_product(product_code):
    return request.env['product.template'].sudo().search([
        ('third_party_id', '=', product_code)
    ], limit=1)


def _process_audit_batch(env, tickets, company, branch, final_audit=False):
    company_ids = list(filter(None, [branch.id, company.id]))
    env = env(su=True, context=dict(env.context, allowed_company_ids=company_ids))

    folios = [t.get('ticket_folio') for t in tickets if t.get('ticket_folio')]
    existing = env['contabilidad_kuale.ticket_monitor'].sudo().search([
        ('ticket_folio', 'in', folios),
        ('company_id', '=', company.id),
        ('branch_id', '=', branch.id),
    ])
    existing_map = {t.ticket_folio: t for t in existing}

    # ── 2. Empleados
    emp_codes = set()
    for t in tickets:
        for f in ('cashier', 'closing_cashier', 'discount_authorized', 'void_authorized'):
            if t.get(f):
                emp_codes.add(str(t.get(f)))
    employee_map = {
        e.cashier_code: e
        for e in env['hr.employee'].sudo().search([('cashier_code', 'in', list(emp_codes))])
    }

    # ── 3. Formas de pago 
    pt_claves = set()
    for t in tickets:
        if t.get('payment_type'):
            pt_claves.add(str(t.get('payment_type')))
        for pay in t.get('payments', []):
            if pay.get('payment_type'):
                pt_claves.add(str(pay.get('payment_type')))
    payment_type_map = {
        pt.third_party_id: pt
        for pt in env['cfdi.claveformadepago'].sudo().search(
            [('third_party_id', 'in', list(pt_claves))]
        )
    }

    # ── 4. Métodos de pago 
    pm_claves = list(set(str(t.get('payment_method')) for t in tickets if t.get('payment_method')))
    payment_method_map = {
        pm.Clave_metodo_de_pago: pm
        for pm in env['cfdi.clavemetododepago'].sudo().search(
            [('Clave_metodo_de_pago', 'in', pm_claves)]
        )
    }

    # ── 5. Descuentos
    disc_claves = list(set(str(d) for t in tickets for d in t.get('discount_ids', []) if d))
    discount_map = {
        d.clave: d
        for d in env['contabilidad_kuale.ticket_discount'].sudo().search(
            [('clave', 'in', disc_claves)]
        )
    } if disc_claves else {}

    # ── 6. Sell types 
    st_claves = list(set(str(t.get('sell_type')) for t in tickets if t.get('sell_type')))
    sell_type_map = {
        st.clave: st
        for st in env['contabilidad_kuale.ticket_sell_types'].sudo().search(
            [('clave', 'in', st_claves)]
        )
    } if st_claves else {}

    # ── 7. Productos 
    prod_codes = list(set(
        str(p.get('third_party_id'))
        for t in tickets for p in t.get('products', [])
        if p.get('third_party_id')
    ))
    product_map = {
        p.third_party_id: p
        for p in env['product.template'].sudo().search(
            [('third_party_id', 'in', prod_codes)]
        )
    } if prod_codes else {}

    # Procesamiento en memoria
    ctx = {
        'env': env,
        'company': company,
        'branch': branch,
        'employee_map': employee_map,
        'payment_type_map': payment_type_map,
        'payment_method_map': payment_method_map,
        'discount_map': discount_map,
        'sell_type_map': sell_type_map,
        'product_map': product_map,
    }

    success, error_details = 0, []
    for ticket in tickets:
        try:
            with env.cr.savepoint():
                _process_single_audit_ticket(env, ticket, existing_map, ctx, final_audit)
                success += 1
        except TicketCreationError as e:
            error_details.append({
                'ticket_folio': ticket.get('ticket_folio'),
                'error': e.message,
                'status': e.status,
            })
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            _logger.error("Audit batch error processing ticket %s: %s\n%s", ticket.get('ticket_folio'), e, tb_str)
            error_details.append({
                'ticket_folio': ticket.get('ticket_folio'),
                'error': f"{str(e)}\n\nTraceback:\n{tb_str[-1000:]}",
                'status': 500,
            })

        env.invalidate_all()

    return {
        'success': success,
        'errors': len(error_details),
        'error_details': error_details,
    }


def _process_single_audit_ticket(env, ticket, existing_map, ctx, final_audit):

    company = ctx['company']
    branch = ctx['branch']
    employee_map = ctx['employee_map']
    payment_type_map = ctx['payment_type_map']
    payment_method_map = ctx['payment_method_map']
    discount_map = ctx['discount_map']

    folio = ticket.get('ticket_folio')
    system_ticket = existing_map.get(folio)

    payment_type = payment_type_map.get(str(ticket.get('payment_type'))) if ticket.get('payment_type') else None
    payment_method = payment_method_map.get(str(ticket.get('payment_method'))) if ticket.get('payment_method') else None
    closing_cashier = (
        employee_map.get(str(ticket.get('closing_cashier')))
        if ticket.get('sell_type') != '1004' and ticket.get('closing_cashier') else None
    )
    incoming_auth = employee_map.get(str(ticket.get('discount_authorized'))) if ticket.get('discount_authorized') else None
    void_authorized = employee_map.get(str(ticket.get('void_authorized'))) if ticket.get('void_authorized') else None

    resolved_discount_ids = [discount_map[str(c)].id for c in ticket.get('discount_ids', []) if str(c) in discount_map]
    discount_ids_cmd = [(6, 0, resolved_discount_ids)]

    payment_lines = [
        (0, 0, {'payment_type': payment_type_map[str(pay['payment_type'])].id, 'amount': pay.get('amount', 0)})
        for pay in ticket.get('payments', [])
        if pay.get('payment_type') and str(pay.get('payment_type')) in payment_type_map
    ]

    product_lines_cmd = [(5, 0, 0)] + [(0, 0, {
        'third_party_id': p.get('third_party_id'),
        'quantity': float(p.get('quantity') or 0),
        'unit_price': float(p.get('unit_price') or 0),
        'discount': float(p.get('discount') or 0),
    }) for p in ticket.get('products', [])]


    # El batch de auditoría solo procesa tickets ya existentes.
    if not system_ticket:
        _logger.info(
            "Audit batch: ticket folio %s no encontrado en el sistema, se omite.",
            ticket.get('ticket_folio'),
        )
        return

    # --- GUARDIA: Ticket vacío en auditoría ---
    # Si el ticket que llega tiene total=0 y sin productos, sólo marcarlo como auditado
    # sin sobreescribir datos del sistema. Evita cascada de inventory_adjustment y
    # creación de sale orders vacías que crasheaban el servidor.
    incoming_total = float(ticket.get('total') or 0.0)
    incoming_products_raw = ticket.get('products')
    if incoming_total == 0.0 and incoming_products_raw is not None and len(incoming_products_raw) == 0:
        _logger.warning(
            "Audit batch: ticket folio %s llega vacío (total=0, products=[]). "
            "Se marca como auditado sin modificar datos del sistema.",
            ticket.get('ticket_folio'),
        )
        system_ticket.sudo().with_context(skip_inventory_adjustment=True).write({
            'modification_status': True,
            'modification_details': 'none',
            'is_empty_ticket': True,
        })
        if final_audit:
            so = system_ticket.sale_order_id
            if so and so.state == 'draft':
                system_ticket.sudo().confirm_related_sale_order()
        return

    # Comparar en memoria
    def _af(v):
        try: return float(v or 0)
        except: return 0.0

    def _aeq(a, b): return abs(_af(a) - _af(b)) < 1e-6

    general_diff, diff_status = False, ''
    sys_pays = system_ticket.payments_ids
    incoming_pays = ticket.get('payments')

    if incoming_pays is not None:
        if len(incoming_pays) != len(sys_pays):
            general_diff, diff_status = True, 'pago'
        else:
            for pay in incoming_pays:
                pt = payment_type_map.get(str(pay.get('payment_type'))) if pay.get('payment_type') else None
                amt = _af(pay.get('amount'))
                if not any(l.payment_type.id == pt.id and _aeq(l.amount, amt) for l in sys_pays if pt):
                    general_diff, diff_status = True, 'pago'
                    break

    if not general_diff:
        if payment_type and payment_type.id != system_ticket.payment_type.id:
            general_diff, diff_status = True, 'pago'
        elif payment_method and payment_method.id != system_ticket.payment_method.id:
            general_diff, diff_status = True, 'pago'
        elif not _aeq(ticket.get('iva', system_ticket.iva), system_ticket.iva):
            general_diff, diff_status = True, 'iva'
        elif (
            not _aeq(ticket.get('total', system_ticket.total), system_ticket.total) or
            not _aeq(ticket.get('subtotal', system_ticket.subtotal), system_ticket.subtotal) or
            not _aeq(ticket.get('discount', system_ticket.discount), system_ticket.discount) or
            ('discount_ids' in ticket and set(resolved_discount_ids) != set(system_ticket.discount_ids.ids))
        ):
            general_diff, diff_status = True, 'monto'

    incoming_products = ticket.get('products')
    if incoming_products is not None:
        line_diff = _compare_product_lines(incoming_products, system_ticket.product_line)
    else:
        line_diff = False

    # Marcar como auditado (sin diferencias — no tocar inventory)
    if not general_diff and not line_diff:
        system_ticket.sudo().with_context(skip_inventory_adjustment=True).write({
            'modification_status': True,
            'modification_details': 'none',
        })
        if final_audit:
            so = system_ticket.sale_order_id
            if so and so.state == 'draft':
                system_ticket.sudo().confirm_related_sale_order()
        return

    if not general_diff and line_diff:
        diff_status = 'auditoria'

    # Hay cambios: crear/actualizar registro de auditoría
    audit_vals = {
        'company_id': company.id,
        'branch_id': branch.id,
        'ticket_folio': folio,
        'closed_date': _to_utc(ticket.get('end_date')),
        'closing_cashier': closing_cashier.id if closing_cashier else None,
        'audit_payment_method': payment_method.id if payment_method else system_ticket.payment_method.id,
        'audit_payment_type': payment_type.id if payment_type else system_ticket.payment_type.id,
        'audit_iva': ticket.get('iva', system_ticket.iva),
        'audit_total': ticket.get('total', system_ticket.total),
        'audit_subtotal': ticket.get('subtotal', system_ticket.subtotal),
        'audit_discount_ids': discount_ids_cmd if 'discount_ids' in ticket else [(6, 0, system_ticket.discount_ids.ids)],
        'audit_discount': ticket.get('discount', system_ticket.discount),
        'audit_discount_authorized': incoming_auth.id if incoming_auth else system_ticket.discount_authorized.id if system_ticket.discount_authorized else None,
        'audit_void_authorized': void_authorized.id if void_authorized else system_ticket.void_authorized.id if system_ticket.void_authorized else None,
        'audit_reprint_number': ticket.get('reprint_number', system_ticket.reprint_number),
        'audit_status': diff_status,
        'audit_ticket_status': '0',
    }

    if incoming_products is not None:
        audit_vals['audit_product_line'] = product_lines_cmd
    else:
        audit_vals['audit_product_line'] = [(5, 0, 0)] + [(0, 0, {
            'third_party_id': p.third_party_id,
            'quantity': p.quantity,
            'unit_price': p.unit_price,
            'discount': p.discount,
        }) for p in system_ticket.product_line]

    if incoming_pays is not None:
        audit_vals['audit_payments_ids'] = [(5, 0, 0)] + payment_lines
    else:
        audit_vals['audit_payments_ids'] = [(5, 0, 0)] + [(0, 0, {
            'payment_type': p.payment_type.id,
            'amount': p.amount,
        }) for p in system_ticket.payments_ids]

    existing_audit = env['contabilidad_kuale.ticket_monitor_audit'].sudo().search([
        ('ticket_folio', '=', folio),
        ('company_id', '=', company.id),
        ('branch_id', '=', branch.id),
    ], limit=1)

    if existing_audit:
        existing_audit.write(audit_vals)
    else:
        env['contabilidad_kuale.ticket_monitor_audit'].sudo().create(audit_vals)

    # Actualizar ticket principal
    update_vals = {
        'payment_type': payment_type.id if payment_type else system_ticket.payment_type.id,
        'payment_method': payment_method.id if payment_method else system_ticket.payment_method.id,
        'date': _to_utc(ticket.get('date')) if ticket.get('date') else system_ticket.date,
        'closed_date': _to_utc(ticket.get('end_date')) if ticket.get('end_date') else None,
        'iva': ticket.get('iva', system_ticket.iva),
        'subtotal': ticket.get('subtotal', system_ticket.subtotal),
        'discount': ticket.get('discount', system_ticket.discount),
        'total': ticket.get('total', system_ticket.total),
        'modification_status': True,
        'modification_details': 'found',
        # Siempre preservar cajeros autorizadores:
        # Si el JSON trae un cajero válido → actualizar; si no → conservar el valor del sistema
        'discount_authorized': incoming_auth.id if incoming_auth else (system_ticket.discount_authorized.id if system_ticket.discount_authorized else None),
        'void_authorized': void_authorized.id if void_authorized else (system_ticket.void_authorized.id if system_ticket.void_authorized else None),
    }

    if 'discount_ids' in ticket:
        update_vals['discount_ids'] = discount_ids_cmd

    if incoming_pays is not None:
        update_vals['payments_ids'] = [(5, 0, 0)] + payment_lines

    # Usar skip_inventory_adjustment para evitar que write() dispare
    # inventory_adjustment() durante la auditoría — esa operación hace
    # action_cancel() en la sale_order y es demasiado lenta para el cron.
    audit_ctx = system_ticket.sudo().with_context(skip_inventory_adjustment=True)
    audit_ctx.write(update_vals)

    if line_diff and incoming_products is not None:
        audit_ctx.write({'product_line': product_lines_cmd})

    if final_audit:
        so = system_ticket.sale_order_id
        if so and so.state == 'draft':
            system_ticket.sudo().confirm_related_sale_order()


class TicketMonitor(http.Controller):

    @http.route('/api/upload/ticket', auth='none', methods=['POST'], type='http', csrf=False)
    def upload_ticket(self, **kw):
        try:
            data = request.httprequest.json
            tickets = data.get('tickets')

            if not tickets:
                return _response(417, "No se encontraron tickets")

            original_count = len(tickets)
            tickets_a_procesar = tickets[:1000]

            if original_count > 1000:
                _logger.warning(
                    "API Ticket: Se recibieron %s tickets, pero el límite es 1000. Se ignorarán %s.",
                    original_count, (original_count - 1000)
                )
            else:
                _logger.info("API Ticket: Procesando %s tickets.", original_count)

            errores = []
            for ticket in tickets_a_procesar:
                try:
                    _create_ticket(ticket)
                except TicketCreationError as e:
                    errores.append({
                        "ticket_folio": ticket.get("ticket_folio"),
                        "company_id": ticket.get("company_id"),
                        "branch_id": ticket.get("branch_id"),
                        "error": e.message,
                        "status": e.status
                    })
                except Exception as e:
                    errores.append({
                        "ticket_folio": ticket.get("ticket_folio"),
                        "company_id": ticket.get("company_id"),
                        "branch_id": ticket.get("branch_id"),
                        "error": str(e),
                        "status": 500
                    })

            if errores:
                return request.make_json_response({
                    "status": 207,
                    "message": "Proceso finalizado con errores",
                    "errors": errores,
                    "procesados": len(tickets_a_procesar)
                }, status=207)

            mensaje = "Todos los tickets fueron creados exitosamente"
            if original_count > 1000:
                mensaje = f"Se procesaron los primeros 1000 tickets (de {original_count} recibidos)."

            return _response(200, mensaje)
        except Exception as e:
            return request.make_json_response({
                'status': 500,
                'message': str(e),
            })

    @http.route('/api/upload/ticket/audit', auth='none', methods=['POST'], type='http', csrf=False)
    def upload_ticket_audit(self, **kw):
        try:
            data = request.httprequest.json
            tickets = data.get('tickets')
            if not tickets:
                return _response(417, "No se encontraron tickets")

            first = tickets[0]
            company = _get_company(first.get('company_id'))
            branch = _get_company(first.get('branch_id'))

            if not company:
                return _response(400, f"Empresa no encontrada: {first.get('company_id')}")
            if not branch:
                return _response(400, f"Sucursal no encontrada: {first.get('branch_id')}")

            job_uuid = str(uuid_lib.uuid4())
            request.env['contabilidad_kuale.ticket_audit_queue'].sudo().create({
                'job_uuid': job_uuid,
                'company_id': company.id,
                'branch_id': branch.id,
                'payload': json.dumps(data, ensure_ascii=False),
                'ticket_count': len(tickets),
                'final_audit': bool(data.get('final_audit')),
            })

            return request.make_json_response({
                'status': 202,
                'message': f'Lote de {len(tickets)} tickets recibido y en cola de procesamiento.',
                'job_uuid': job_uuid,
            }, status=202)

        except Exception as e:
            return request.make_json_response({
                'status': 500,
                'message': str(e),
            }, status=500)

    @http.route('/api/upload/ticket/audit/status/<string:job_uuid>',
                auth='none', methods=['GET'], type='http', csrf=False)
    def audit_job_status(self, job_uuid, **kw):
        """Permite que el POS consulte el resultado de un job de auditoría."""
        job = request.env['contabilidad_kuale.ticket_audit_queue'].sudo().search([
            ('job_uuid', '=', job_uuid)
        ], limit=1)
        if not job:
            return _response(404, "Job no encontrado")

        errors = []
        if job.result_summary and job.status == 'done':
            try:
                errors = json.loads(job.result_summary)
            except Exception:
                pass

        return request.make_json_response({
            'status': 200,
            'job_uuid': job_uuid,
            'job_status': job.status,
            'ticket_count': job.ticket_count,
            'success_count': job.success_count,
            'error_count': job.error_count,
            'processed_at': str(job.processed_at) if job.processed_at else None,
            'errors': errors,
        }, status=200)

    @http.route('/api/validate/catalog', auth='none', methods=['POST'], type='http', csrf=False)
    def validate_catalog(self, **kw):
        data = request.httprequest.json
        company = _get_company(data['company_id'])
        branch = _get_company(data['branch_id'])
        catalog_type = int(data.get('tipoCatalogo'))
        catalog = data.get('catalogo')

        if not company:
            return _response(400, "Empresa no encontrada")
        if not branch:
            return _response(400, "Sucursal no encontrada")
        if catalog_type not in [1, 2, 3, 4, 5, 6]:
            return _response(400, "Tipo de catálogo inválido")

        if not isinstance(catalog, list):
            return _response(400, "El catálogo debe ser una lista")
        catalog_names = {
            1: "Productos",
            2: "Descuentos",
            3: "Cajeros",
            4: "Formas de pago",
            5: "Métodos de pago",
            6: "Tipos de venta"
        }

        try:
            validators = {
                1: _get_product,
                2: _get_discount,
                3: _get_employee,
                4: _get_payment_type,
                5: _get_payment_method,
                6: _get_sell_type
            }

            validator = validators[catalog_type]

            details = []
            for item in catalog:
                clave = item.get('Clave')
                record = validator(clave)
                if record:
                    continue
                else:
                    details.append(item)
            return _response(200,
                             f"Validación completa - datos no encontrados en el catálogo: {catalog_names[catalog_type]}",
                             details)
        except Exception as e:
            return _response(500, f"Error interno: {str(e)}")
