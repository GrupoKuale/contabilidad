{
    'name': 'Contabilidad_Kuale',
    'description': '',
    'summary': """Contabilidad""",
    'website': 'www.dwit.mx',
    'author': 'DWIT',
    'version': '0.1',
    'depends': ['base', 'web', 'account', 'sale', 'purchase', 'account_check_printing', 'analytic', 'spreadsheet',
                'hr_contract', 'hr_expense',
                'hr_holidays', 'portal', 'payment', 'stock', 'delivery', 'stock_delivery', 'sale_management',
                'contacts',
                'reclutamiento__kuale', 'spiffy_theme_backend', 'mail'],
    'data': [
        # security
        'security/account_budget_security.xml',
        'security/security.xml',
        'security/hr_payroll_security.xml',
        'security/ir.model.access.csv',

        # base accounting budget
        'views/account_analytic_account_views.xml',
        'views/account_budget_views.xml',

        'report/sat_xml_invoice_report.xml',
        'report/sat_xml_invoice_template.xml',

        # base accounting kit
        'data/account_financial_report_data.xml',
        'data/cash_flow_data.xml',
        'data/followup_levels.xml',
        'data/multiple_invoice_data.xml',
        'data/recurring_entry_cron.xml',
        'data/account_pdc_data.xml',
        'data/ticket_audit_queue_cron.xml',
        'data/async_global_invoice_cron.xml',
        'views/reports_config_view.xml',
        'views/accounting_menu.xml',
        'views/account_group.xml',
        'views/credit_limit_view.xml',
        'views/account_configuration.xml',
        'views/res_config_view.xml',
        'views/account_followup.xml',
        'views/followup_report.xml',
        # WARNING: THIS WAS REMOVED TO AVOID REPORT CONFICTS WHILE CREATING NEW REPORTS
        # 'wizard/asset_depreciation_confirmation_wizard_views.xml',
        'wizard/asset_modify_views.xml',
        'views/account_asset_views.xml',
        'views/account_move_views.xml',
        'views/product_template_views.xml',
        'views/multiple_invoice_layout_view.xml',
        'views/multiple_invoice_form.xml',
        'views/account_payment_view.xml',
        'views/sat_product_codes_views.xml',
        'views/sat_file_views.xml',
        'views/sat_user_add_views.xml',
        'views/sat_add_contpaq_views.xml',

        # hr payroll
        'data/hr_payroll_sequence.xml',
        'data/hr_payroll_data.xml',
        'wizard/hr_payslips_employees_views.xml',
        'wizard/payslip_lines_contribution_register_views.xml',
        'report/hr_payroll_report.xml',
        'report/report_contribution_register_templates.xml',
        'report/report_payslip_templates.xml',
        'report/report_payslip_details_templates.xml',
        'views/hr_leave_type_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_salary_rule_views.xml',
        'views/hr_salary_rule_category_views.xml',
        'views/hr_contribution_register_views.xml',
        'views/hr_payroll_structure_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_payslip_line_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/res_config_settings_views.xml',

        # Catalogos SAT
        'views/catalogos/claveprodservcp.xml',
        'views/catalogos/claveprodserv.xml',
        'views/catalogos/claveunidadpeso.xml',
        'views/catalogos/claveunidad.xml',
        'views/catalogos/clavecolonia.xml',
        'views/catalogos/clavelocalidad.xml',
        'views/catalogos/clavemunicipio.xml',
        'views/catalogos/claveestado.xml',
        'views/catalogos/clavepais.xml',
        'views/catalogos/clavetipopermiso.xml',
        'views/catalogos/claveconfigauto.xml',
        'views/catalogos/usuariosapp.xml',
        'views/catalogos/claveregimenfiscal.xml',
        'views/catalogos/clavesubtiporemo.xml',
        'views/catalogos/clavepartetransporte.xml',
        'views/catalogos/clavematerialpeligroso.xml',
        'views/catalogos/clavetipoembalaje.xml',
        'views/catalogos/claveformadepago.xml',
        'views/catalogos/clavemetododepago.xml',
        'views/catalogos/clavemoneda.xml',
        'views/catalogos/claveusocfdi.xml',
        'views/catalogos/claveobjetoimp.xml',
        'views/catalogos/claveimpuesto.xml',
        'views/catalogos/claveexportacion.xml',
        'views/catalogos/update_prodserv_cp.xml',
        'views/catalogos/sell_type.xml',
        'views/catalogos/codigo_agrupador_sat.xml',
        'views/catalogos/payment_account_types.xml',

        # fabricacion
        'views/product_cost_history.xml',
        'views/product_fabrication_batch.xml',

        # transfer
        'views/product_branch_transfer.xml',

        # sells
        'views/sale_order.xml',
        
        # general
        'views/additional_files.xml',
        'views/invoice_webview.xml',
        'views/res_company.xml',
        'views/invoice_report.xml',
        'views/invoice_report_template.xml',
        'views/purchase_managment_view.xml',

        'views/invoice_complaint_ticket.xml',
        'views/ticket_monitor_summary_history.xml',
        'views/ticket_monitor_summary_view.xml',
        'views/ticket_monitor_view.xml',
        'views/ticket_monitor_audit_view.xml',
        
        'views/stock_inventory.xml',
        'views/sale_summary_report_pdf.xml',
        'wizard/sale_summary_report_wizard.xml',
        'views/sales_system_summary_dashboard.xml',
        'views/ticket_discount.xml',
        'views/cash_cut.xml',
        'views/res_users.xml',
        'views/bank_transaction.xml',
        'views/product_complement_view.xml',
        'views/res_partner.xml',
        'views/product_supplier_info_sumup.xml',

        # pre-data
        'data/regimen_fiscal_data.xml',
        'data/cfdi_clave_uso_data.xml',
        'data/clave_moneda_data.xml',
        'data/clave_objeto_impuesto.xml',
        'data/mail_authorization_request.xml',
        'data/markup.xml',

        # test
        'wizard/trial_balance_test.xml',
        # checkId
        'views/checkid_views.xml',
        #conciliaciones
        'views/reconciliation_view.xml',
        'views/banks_importer_view.xml',
        #price history
        'views/pixl_price_history.xml',

        #wizard cancellation invoice
        'views/ticket_invoice_cancellation.xml',

        #payment batches
        'data/sequence_account_move.xml',
        'views/account_move_batch_bank.xml',

        'views/approvals_dashboard.xml',
        'data/approval_dashboard.xml',
        'views/verifications_dashboard.xml',
        'data/verification_dashboard.xml',
        'data/sat_tipo_operaciones.xml',
        #SAT
        'views/sat_add_external_document_views.xml',
        #Sat Cron
        'views/sat_cron.xml',

        #View
        'wizard/sat_xml_view_wizard_views.xml',
        'wizard/sat_xml_match_wizard_views.xml',
        'wizard/share_category_confirm_wizard_views.xml',
        'wizard/ticket_exterior_wizard_view.xml',
        
        #STP
        'views/stp_views.xml',
        'data/sequence_stp.xml',
        
        # menuitems
        'views/contacts_menu.xml',
        'views/custom_billing_view.xml',
        'views/ticket_audit_queue_view.xml',

    ],
    "assets": {
        "web.assets_backend": [
            'contabilidad_kuale/static/src/satinvoices/**/*',
            'contabilidad_kuale/static/src/js/product_by_branch.js',
            'contabilidad_kuale/static/src/js/pdf_generator.js',
            'contabilidad_kuale/static/src/templates/report_pdf_template.html',
            'contabilidad_kuale/static/src/kuale_trial_balance/kualeTrialBalance.js',
            'contabilidad_kuale/static/src/kuale_trial_balance/kualeTrialBalanceController.xml',
            'contabilidad_kuale/static/src/kuale_trial_balance/kualeTrialBalanceRenderer.xml',
            'contabilidad_kuale/static/src/kuale_income_statement/kualeIncomeStatement.js',
            'contabilidad_kuale/static/src/kuale_income_statement/kualeIncomeStatementController.xml',
            'contabilidad_kuale/static/src/kuale_income_statement/kualeIncomeStatementRenderer.xml',
            'contabilidad_kuale/static/src/kuale_finacial_position/kualeFinancialPosition.js',
            'contabilidad_kuale/static/src/kuale_finacial_position/kualeFinancialPositionController.xml',
            'contabilidad_kuale/static/src/kuale_finacial_position/kualeFinancialPositionRenderer.xml',
            'contabilidad_kuale/static/src/kuale_static_balance/kualeStaticBalance.js',
            'contabilidad_kuale/static/src/kuale_static_balance/kualeStaticBalanceController.xml',
            'contabilidad_kuale/static/src/kuale_static_balance/kualeStaticBalanceRenderer.xml',
            'contabilidad_kuale/static/src/kuale_aux_movements/kualeAuxMovements.js',
            'contabilidad_kuale/static/src/kuale_aux_movements/kualeAuxMovementController.xml',
            'contabilidad_kuale/static/src/kuale_aux_movements/kualeAuxMovementRenderer.xml',
            'contabilidad_kuale/static/src/js/switch_company_menu.js',
            'contabilidad_kuale/static/src/js/approvals_dashboard.js',
            'contabilidad_kuale/static/src/js/verifications_dashboard.js',

              # vista Contpaqi
            'contabilidad_kuale/static/src/css/add_contpaq_view.css',
            'contabilidad_kuale/static/src/js/add_contpaq_view.js',
            'contabilidad_kuale/static/src/xml/add_contpaq_view.xml',
            'contabilidad_kuale/static/src/js/cfdi_preview.js',
            'contabilidad_kuale/static/src/xml/cfdi_preview_dialog.xml',

        ],
        "web.contabilidad_kuale_invoice_backend": [
            'contabilidad_kuale/static/src/js/invoice_website.js',
        ],
        "web.assets_frontend": [
            'contabilidad_kuale/static/src/img/Icono_PDF.svg',
            '/contabilidad_kuale/static/src/img/Icono_XML.svg',
            'contabilidad_kuale/static/src/img/Icono_check.svg',
        ]
    },
    'post_init_hook': 'post_init_create_production_locations',
    'installable': True,
    'application': True,
    'auto_install': False,
}
