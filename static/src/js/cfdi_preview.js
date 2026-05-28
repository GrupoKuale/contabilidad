/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class CFDIPreviewDialog extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            invoiceData: null,
            loading: true,
            
            // Campos que se pueden mostrar/ocultar
            visibleFields: {
                // Datos del comprobante
                version: true,
                serie: true,
                folio: true,
                fecha: true,
                formaPago: true,
                metodoPago: true,
                tipoComprobante: true,
                lugarExpedicion: true,
                moneda: true,
                tipoCambio: true,
                
                // Emisor
                emisorRFC: true,
                emisorNombre: true,
                emisorRegimenFiscal: true,
                
                // Receptor
                receptorRFC: true,
                receptorNombre: true,
                receptorUsoCFDI: true,
                receptorDomicilio: true,
                
                // Conceptos
                conceptos: true,
                conceptoClave: true,
                conceptoUnidad: true,
                conceptoCantidad: true,
                conceptoDescripcion: true,
                conceptoValorUnitario: true,
                conceptoImporte: true,
                conceptoImpuestos: true,
                
                // Totales
                subtotal: true,
                descuentos: true,
                impuestos: true,
                total: true,
                
                // Información fiscal
                uuid: true,
                fechaCertificacion: true,
                certificadoEmisor: true,
                certificadoSAT: true,
            },
        });

        onWillStart(async () => {
            await this.loadInvoiceData();
        });
    }

    async loadInvoiceData() {
        try {
            const invoiceId = this.props.invoiceId;
            const data = await this.orm.call(
                "sat.xml.invoices",
                "get_invoice_preview_data",
                [invoiceId]
            );
            
            this.state.invoiceData = data;
            this.state.loading = false;
        } catch (error) {
            this.notification.add("Error al cargar la vista preliminar", {
                type: "danger",
            });
            console.error("Error:", error);
            this.state.loading = false;
        }
    }

    toggleField(fieldName) {
        this.state.visibleFields[fieldName] = !this.state.visibleFields[fieldName];
    }

    toggleSection(section) {
        const fields = this.getSectionFields(section);
        const allVisible = fields.every(f => this.state.visibleFields[f]);
        
        fields.forEach(f => {
            this.state.visibleFields[f] = !allVisible;
        });
    }

    getSectionFields(section) {
        const sections = {
            comprobante: ['version', 'serie', 'folio', 'fecha', 'formaPago', 
                         'metodoPago', 'tipoComprobante', 'lugarExpedicion', 
                         'moneda', 'tipoCambio'],
            emisor: ['emisorRFC', 'emisorNombre', 'emisorRegimenFiscal'],
            receptor: ['receptorRFC', 'receptorNombre', 'receptorUsoCFDI', 'receptorDomicilio'],
            conceptos: ['conceptos', 'conceptoClave', 'conceptoUnidad', 
                       'conceptoCantidad', 'conceptoDescripcion', 
                       'conceptoValorUnitario', 'conceptoImporte', 'conceptoImpuestos'],
            totales: ['subtotal', 'descuentos', 'impuestos', 'total'],
            fiscal: ['uuid', 'fechaCertificacion', 'certificadoEmisor', 'certificadoSAT'],
        };
        return sections[section] || [];
    }

    async generatePDF() {
        try {
            this.notification.add("Generando PDF...", { type: "info" });
            
            const visibleFields = JSON.parse(JSON.stringify(this.state.visibleFields));

            const result = await this.orm.call(
                "sat.xml.invoices",
                "action_generate_xml_pdf_with_fields", 
                [this.props.invoiceId, visibleFields]
            );
            
            if (result && result.url) {
                window.location.href = result.url; 
                this.notification.add("PDF descargado exitosamente", { type: "success" });
            }
        } catch (error) {
            this.notification.add("Error al generar el PDF: " + error.message, { type: "danger" });
            console.error("Error:", error);
        }
    }

    close() {
        this.props.close();
    }
}

CFDIPreviewDialog.template = "sat_cfdi.CFDIPreviewDialog";
CFDIPreviewDialog.props = {
    invoiceId: Number,
    close: Function,
};

registry.category("dialogs").add("cfdi_preview_dialog", CFDIPreviewDialog);

export default CFDIPreviewDialog;
