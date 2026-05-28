/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillUnmount, onMounted } from "@odoo/owl";
import { modalService } from "@web/core/modal/modal_service";

class PreviewPDFModal extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.fileId = this.props.fileId;

        onWillUnmount(async () => {
            await this.rpc(`/custom/invoice/delete_temp_pdf/${this.fileId}`, {});
        });
    }

    static template = "my_module.PreviewPDFModal";
}

PreviewPDFModal.props = ["fileId"];

registry.category("actions").add("preview_temp_pdf", (env, action) => {
    const { file_id } = action.params;
    env.services.modal.add(PreviewPDFModal, { fileId: file_id });
});
