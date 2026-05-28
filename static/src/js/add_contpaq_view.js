/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Layout } from "@web/search/layout";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
import CFDIPreviewDialog from "./cfdi_preview";
import { _t } from "@web/core/l10n/translation";

// ========== Controlador principal ==========
export class ADDContpaqController extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        this.state = useState({

            showLeftPanel: true,
            showRightPanel: true,
            
            presets: [],
            currentPresetId: null,

            xmlRecibidosExpanded: true,
            xmlEmitidosExpanded: false,

            activeFilters: {
                documentType: null,
                documentGroup: null,
                addStatus: 'available',
            },

            rightPanelChecks: {
                add: true,
                cfdiRelacionado: false,
                cfdiRelacionadoRetencion: false,
                comprobante: true,
                conceptoFactura: false,
                conceptoImpuestoRetencion: false,
                conceptoImpuestoTraslado: false,
                impuestosLocales: false,
                totalImpuestosComprobante: false,
            },

            visibleFields: [
                'factura_fecha',
                'factura_tipo',
                'factura_serie',
                'factura_folio',
                'rfc_emisor',
                'nombre_emisor',
                'factura_moneda',
                'factura_tipo_cambio',
                'factura_total'
            ],
            
            availableFields: [],
            invoices: [],
            selectedInvoices: [],

            stats: {
                totalRegistros: 0,
                documentosSeleccionados: 0,
                importeTotalSeleccionado: 0,
            },

            dateFrom: this.getDefaultDateFrom(),
            dateTo: this.getDefaultDateTo(),
        });

       onWillStart(async () => {
            await Promise.all([
                this.loadAvailableFields(),
                this.loadPresets(),
                this.loadInvoices()
            ]);
        });
    }

    getDefaultDateFrom() {
        const date = new Date();
        date.setDate(1);
        return date.toISOString().split('T')[0];
    }

    getDefaultDateTo() {
        const date = new Date();
        return date.toISOString().split('T')[0];
    }

    async loadAvailableFields() {
        try {
            const fields = await this.orm.call(
                "sat.xml.invoices",
                "get_available_fields",
                []
            );
            this.state.availableFields = fields || [];
        } catch (error) {
            console.error("Error cargando campos:", error);
        }
    }

    async loadInvoices() {
        const domain = this.buildDomain();
        const fields = ['id', 'tfd_uuid', ...this.state.visibleFields];

        this.state.invoices = await this.orm.searchRead(
            "sat.xml.invoices",
            domain,
            fields,
            { order: "factura_fecha desc" }
        );
        this.updateStats();
    }

    buildDomain() {
        const domain = [];

        if (this.state.activeFilters.documentType) {
            domain.push(['document_type', '=', this.state.activeFilters.documentType]);
        }

        if (this.state.activeFilters.documentGroup) {
            domain.push(['document_group', '=', this.state.activeFilters.documentGroup]);
        }

        if (this.state.activeFilters.addStatus === 'available') {
            domain.push(['add_status', '=', 'available']);
            domain.push(['add_user_id', '=', false]);
        } else if (this.state.activeFilters.addStatus === 'my_add') {
            domain.push(['add_user_id', '=', this.env.services.user.userId]);
            domain.push(['add_status', 'in', ['locked', 'processed']]);
        }

        if (this.state.dateFrom) {
            domain.push(['factura_fecha', '>=', this.state.dateFrom]);
        }

        if (this.state.dateTo) {
            domain.push(['factura_fecha', '<=', this.state.dateTo]);
        }

        return domain;
    }

    updateStats() {
        this.state.stats.totalRegistros = this.state.invoices.length;
        this.state.stats.documentosSeleccionados = this.state.selectedInvoices.length;
        this.state.stats.importeTotalSeleccionado = this.state.selectedInvoices.reduce(
            (sum, id) => {
                const inv = this.state.invoices.find(i => i.id === id);
                return sum + (inv?.factura_total || 0);
            },
            0
        );
    }

    async onClickRecibidos() {
        this.state.activeFilters.documentType = 'recibido';
        this.state.activeFilters.documentGroup = null;
        this.state.xmlRecibidosExpanded = !this.state.xmlRecibidosExpanded;
        await this.loadInvoices();
    }

    async onClickEmitidos() {
        this.state.activeFilters.documentType = 'emitido';
        this.state.activeFilters.documentGroup = null;
        this.state.xmlEmitidosExpanded = !this.state.xmlEmitidosExpanded;
        await this.loadInvoices();
    }

    async onClickGroup(type, group) {
        this.state.activeFilters.documentType = type;
        this.state.activeFilters.documentGroup = group;
        await this.loadInvoices();
    }

    async onClickMiADD() {
        this.state.activeFilters.documentType = null;
        this.state.activeFilters.documentGroup = null;
        this.state.activeFilters.addStatus = 'my_add';
        await this.loadInvoices();
    }

    async onClickDisponibles() {
        this.state.activeFilters.addStatus = 'available';
        await this.loadInvoices();
    }

    onSelectInvoice(invoiceId, isChecked) {
        if (isChecked) {
            this.state.selectedInvoices.push(invoiceId);
        } else {
            const index = this.state.selectedInvoices.indexOf(invoiceId);
            if (index > -1) {
                this.state.selectedInvoices.splice(index, 1);
            }
        }
        this.updateStats();
    }

    onSelectAll(isChecked) {
        if (isChecked) {
            this.state.selectedInvoices = this.state.invoices.map(inv => inv.id);
        } else {
            this.state.selectedInvoices = [];
        }
        this.updateStats();
    }

    async onCargarXML() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'sat.uploads',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
        });
    }

    async onAgregarADD() {
        if (this.state.selectedInvoices.length === 0) {
            this.notification.add(
                "Debe seleccionar al menos un documento",
                { type: "warning" }
            );
            return;
        }

        try {
            const userAdd = await this.orm.call(
                "sat.user.add",
                "get_or_create_user_add",
                []
            );

            await this.orm.call(
                "sat.user.add",
                "action_add_documents",
                [userAdd.id],
                { invoice_ids: this.state.selectedInvoices }
            );

            this.notification.add(
                `${this.state.selectedInvoices.length} documentos agregados a su ADD`,
                { type: "success" }
            );

            this.state.selectedInvoices = [];
            await this.loadInvoices();
        } catch (error) {
            this.notification.add(
                "Error al agregar documentos: " + error.message,
                { type: "danger" }
            );
        }
    }

    async onExportarXML() {
        if (this.state.selectedInvoices.length === 0) {
            this.notification.add(
                "Debe seleccionar al menos un documento",
                { type: "warning" }
            );
            return;
        }

        const userAdd = await this.orm.call(
            "sat.user.add",
            "get_or_create_user_add",
            []
        );

        await this.orm.call(
            "sat.user.add",
            "action_export_xmls",
            [userAdd.id],
            { invoice_ids: this.state.selectedInvoices }
        );
    }

    async onDateChange() {
        await this.loadInvoices();
    }

    async onOpenPreview(invoiceId) {
        this.dialog.add(CFDIPreviewDialog, {
            invoiceId: invoiceId,
        });
    }

    async onVerXML(invoiceId) {
        window.open(`/web/content?model=sat.xml.invoices&field=xml_file&id=${invoiceId}&download=true`);
    }

    async onGenerarPDF(invoiceId) {
        try {
            this.notification.add(
                "Generando PDF...",
                { type: "info" }
            );

            const action = await this.orm.call(
                "sat.xml.invoices",
                "action_generate_xml_pdf",
                [[invoiceId]]
            );

            if (action && action.type === 'ir.actions.act_url') {
                window.open(action.url, '_self');
            } else if (action) {
                this.action.doAction(action);
            }
        } catch (error) {
            console.error('Error generando PDF:', error);
            this.notification.add(
                "Error al generar PDF: " + (error.data?.message || error.message),
                { type: "danger" }
            );
        }
    }

    async onOpenFieldSelector() {
        this.dialog.add(FieldSelectorDialog, {
            orm: this.orm,
            selectedFields: this.state.visibleFields,
            onConfirm: (fields) => this.onFieldsSelected(fields),
        });
    }

    async onFieldsSelected(fields) {
        this.state.visibleFields = fields;
        await this.loadInvoices();
        this.notification.add(
            `Vista actualizada con ${fields.length} campos`,
            { type: "success" }
        );
    }

    async onExportToExcel() {
        if (this.state.selectedInvoices.length === 0) {
            this.notification.add(
                "Debe seleccionar al menos un documento",
                { type: "warning" }
            );
            return;
        }

        try {
            this.notification.add(
                "Preparando archivo Excel...",
                { type: "info" }
            );

            const result = await this.orm.call(
                "sat.xml.invoices",
                "action_export_to_excel",
                [this.state.selectedInvoices, this.state.visibleFields]
            );

            if (result && result.url) {
                window.open(result.url, '_blank');
                this.notification.add(
                    `Excel descargado (${this.state.selectedInvoices.length} registros)`,
                    { type: "success" }
                );
            }
        } catch (error) {
            console.error("Error exportando:", error);
            this.notification.add(
                "Error al exportar: " + (error.data?.message || error.message),
                { type: "danger" }
            );
        }
    }

    toggleLeftPanel() {
        this.state.showLeftPanel = !this.state.showLeftPanel;
    }

    toggleRightPanel() {
        this.state.showRightPanel = !this.state.showRightPanel;
    }


    async loadPresets() {
        try {
            this.state.presets = await this.orm.call("sat.add.view.preset", "get_user_presets", []);
        } catch (e) {
            console.error("Error cargando presets", e);
        }
    }

    async onSavePreset() {
        const name = prompt("Nombre para esta vista personalizada:");
        if (!name) return;

        try {
            await this.orm.call("sat.add.view.preset", "create_preset", [
                name, 
                this.state.visibleFields 
            ]);
            
            this.notification.add("Vista guardada correctamente", { type: "success" });
            await this.loadPresets(); 
        } catch (error) {
            this.notification.add("Error al guardar vista: " + error.message, { type: "danger" });
        }
    }

    async onDeletePreset(presetId, event) {
        event.stopPropagation(); 
        if (!confirm("¿Eliminar esta vista guardada?")) return;

        try {
            await this.orm.call("sat.add.view.preset", "delete_preset", [presetId]);
            await this.loadPresets();
            this.state.currentPresetId = null;
        } catch (error) {
            this.notification.add("Error eliminando vista", { type: "danger" });
        }
    }

    onApplyPreset(event) {
        const presetId = parseInt(event.target.value);
        if (!presetId) return;

        const preset = this.state.presets.find(p => p.id === presetId);
        if (preset) {
            this.state.visibleFields = preset.fields;
            this.state.currentPresetId = presetId;
            this.loadInvoices(); 
            this.notification.add(`Vista "${preset.name}" aplicada`, { type: "success" });
        }
    }toggleLeftPanel() {
        this.state.showLeftPanel = !this.state.showLeftPanel;
    }

    toggleRightPanel() {
        this.state.showRightPanel = !this.state.showRightPanel;
    }

    async loadPresets() {
        try {
            this.state.presets = await this.orm.call("sat.add.view.preset", "get_user_presets", []);
        } catch (e) {
            console.error("Error cargando presets", e);
        }
    }

    async onSavePreset() {
        const name = prompt("Nombre para esta vista personalizada:");
        if (!name) return;

        try {
            await this.orm.call("sat.add.view.preset", "create_preset", [
                name, 
                this.state.visibleFields 
            ]);
            
            this.notification.add("Vista guardada correctamente", { type: "success" });
            await this.loadPresets(); 
        } catch (error) {
            this.notification.add("Error al guardar vista: " + error.message, { type: "danger" });
        }
    }

    async onDeletePreset(presetId, event) {
        event.stopPropagation(); 
        if (!confirm("¿Eliminar esta vista guardada?")) return;

        try {
            await this.orm.call("sat.add.view.preset", "delete_preset", [presetId]);
            await this.loadPresets();
            this.state.currentPresetId = null;
        } catch (error) {
            this.notification.add("Error eliminando vista", { type: "danger" });
        }
    }

    onApplyPreset(event) {
        const presetId = parseInt(event.target.value);
        if (!presetId) return;

        const preset = this.state.presets.find(p => p.id === presetId);
        if (preset) {
            this.state.visibleFields = preset.fields;
            this.state.currentPresetId = presetId;
            this.loadInvoices();
            this.notification.add(`Vista "${preset.name}" aplicada`, { type: "success" });
        }
    }

    getFieldLabel(fieldName) {
        const field = this.state.availableFields.find(f => f.name === fieldName);
        return field ? field.label : fieldName;
    }

    getFieldValue(invoice, fieldName) {
        const value = invoice[fieldName];
        
        if (value === undefined || value === null || value === false) {
            return '-';
        }
        
        if (fieldName.includes('total') || fieldName.includes('subtotal') || fieldName.includes('importe')) {
            return `$${parseFloat(value).toFixed(2)}`;
        }
        
        if (typeof value === 'object' && value.id) {
            return value.name || value.display_name || value.id;
        }
        
        return value;
    }
}

class FieldSelectorDialog extends Component {
    static template = "contabilidad_kuale.FieldSelectorDialog";
    static props = {
        orm: Object,
        selectedFields: Array,
        close: Function,
        onConfirm: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.state = useState({
            selected: new Set(this.props.selectedFields),
            availableFields: [],
            loading: true,
        });

        onWillStart(async () => {
            await this.loadFields();
        });
    }

    async loadFields() {
        try {
            const fields = await this.orm.call(
                "sat.xml.invoices",
                "get_available_fields",
                []
            );
            this.state.availableFields = fields || [];
            this.state.loading = false;
        } catch (error) {
            console.error("Error cargando campos:", error);
            this.state.loading = false;
            this.notification.add(
                "Error cargando campos: " + (error.data?.message || error.message),
                { type: "danger" }
            );
        }
    }

    toggleField(fieldName) {
        if (this.state.selected.has(fieldName)) {
            this.state.selected.delete(fieldName);
        } else {
            this.state.selected.add(fieldName);
        }
    }

    isSelected(fieldName) {
        return this.state.selected.has(fieldName);
    }

    onConfirm() {
        const fields = Array.from(this.state.selected);
        if (fields.length === 0) {
            this.notification.add(
                "Debe seleccionar al menos un campo",
                { type: "warning" }
            );
            return;
        }
        this.props.onConfirm(fields);
        this.props.close();
    }

    onCancel() {
        this.props.close();
    }
}

ADDContpaqController.components = { Layout };
ADDContpaqController.template = "contabilidad_kuale.ADDContpaqView";

export const ADDContpaqView = {
    type: "add_contpaq",
    display_name: "ADD ContPaq",
    icon: "fa fa-th-list",
    multiRecord: true,
    Controller: ADDContpaqController,
    props: (genericProps, view) => {
        const { arch, relatedModels, resModel } = genericProps;
        return {
            ...genericProps,
            Model: view.Model,
            buttonTemplate: arch.getAttribute("button_template"),
        };
    },
};

registry.category("views").add("add_contpaq", ADDContpaqView);
