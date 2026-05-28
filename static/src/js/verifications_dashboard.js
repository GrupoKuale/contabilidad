/** @odoo-module **/

import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { registry } from "@web/core/registry";

export class VerificationsKanbanRecord extends KanbanRecord {}

export class VerificationsKanbanRenderer extends KanbanRenderer {}
VerificationsKanbanRenderer.components = {
    ...KanbanRenderer.components,
    KanbanRecord: VerificationsKanbanRecord,
};

export const VerificationsDashboardKanbanView = {
    ...kanbanView,
    Renderer: VerificationsKanbanRenderer,
};

registry.category("views").add("verifications_dashboard_kanban", VerificationsDashboardKanbanView);
