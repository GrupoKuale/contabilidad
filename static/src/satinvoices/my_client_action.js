/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ControlPanel } from "@web/search/control_panel/control_panel";

import { Component, onWillStart, useState, useEffect } from "@odoo/owl";

class MyClientAction extends Component {
    setup() {
        this.controlPanelDisplay = {};
        this.state = useState({ activeDashboard: undefined });
    }
}
MyClientAction.template = "base_accounting_kit.clientaction";
MyClientAction.components = {
    ControlPanel,
};

// remember the tag name we put in the first step
registry.category("actions").add("my_client_action", MyClientAction);