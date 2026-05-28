/** @odoo-module **/

import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { registry } from "@web/core/registry";

export class ApprovalsKanbanRecord extends KanbanRecord {}

export class ApprovalsKanbanRenderer extends KanbanRenderer {}
ApprovalsKanbanRenderer.components = {
    ...KanbanRenderer.components,
    KanbanRecord: ApprovalsKanbanRecord,
};

export const ApprovalsDashboardKanbanView = {
    ...kanbanView,
    Renderer: ApprovalsKanbanRenderer,
};

registry.category("views").add("approvals_dashboard_kanban", ApprovalsDashboardKanbanView);
