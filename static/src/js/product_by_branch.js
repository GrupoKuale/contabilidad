/** @odoo-module */

import { KanbanController } from "@web/views/kanban/kanban_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { registry } from "@web/core/registry";
import {KanbanRenderer} from "@web/views/kanban/kanban_renderer";
import { useService } from "@web/core/utils/hooks";


console.log("📌 CustomKanbanRenderer cargado");
class CustomKanbanRenderer extends KanbanRenderer{
    setup(){
        super.setup();
        console.log("✅ CustomKanbanRenderer: setup ejecutado")
        this.company = useService("company");
        console.log('session: ', this.company.activeCompanyIds)
        const domainValue = this.company.activeCompanyIds
        let domain = [["company_id", "in", domainValue]];
        console.log("🔍 Filtrando con Enter:", domain);
        this.env.searchModel.splitAndAddDomain(domain);

    }

}

class CustomKanbanController extends KanbanController {

}


export const customKanbanView = {
    ...kanbanView,
    Controller: CustomKanbanController,
    Renderer: CustomKanbanRenderer,
};

registry.category("views").add("custom_kanban", customKanbanView);