/** @odoo-module **/

import {Layout} from "@web/search/layout";
import {useService} from "@web/core/utils/hooks";
import {Component, onWillStart, useState, onMounted} from "@odoo/owl";
import {KeepLast} from "@web/core/utils/concurrency";
import {registry} from "@web/core/registry";
import {loadJS, loadCSS} from "@web/core/assets";
import {PDFReportGenerator} from "../js/pdf_generator";


class KualeAuxMovementModel {
    constructor(orm) {
        this.orm = orm;
        this.keeplast = new KeepLast();
        this.state = useState({
            groups: [],
            parentByPath: new Map(),
            fromDate: this.getStartOfMonth(),
            toDate: this.getToday(),
            codeFrom: "",
            codeTo: "",
        });
    }

    getStartOfMonth() {
        const d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().split("T")[0];
    }

    getToday() {
        return new Date().toISOString().split("T")[0];
    }

    async load(company_id = null, branch_id = null, sat_nivel = null, includeEmpty = true,
               fromDate = this.state.fromDate, toDate = this.state.toDate,
               codeFrom = this.state.codeFrom, codeTo = this.state.codeTo) {
        this.state.fromDate = fromDate;
        this.state.toDate = toDate;
        this.state.codeFrom = codeFrom;
        this.state.codeTo = codeTo;

        const baseCompanyDom = company_id ? [["company_id", "=", company_id]] : [];
        const baseBranchDom = branch_id ? [["branch_id", "=", parseInt(branch_id)]] : [];
        const groupDomain = [...baseCompanyDom];
        if (sat_nivel) groupDomain.push(["sat_nivel", "=", sat_nivel]);
        if (codeFrom) groupDomain.push(["code_prefix_start", ">=", codeFrom]);
        if (codeTo) groupDomain.push(["code_prefix_start", "<=", codeTo]);

        // 1) Grupos
        const groups = await this.orm.searchRead("account.group", groupDomain,
            ["id", "name", "group_id", "code_prefix_start", "sat_nivel"]);

        // 2) Cuentas
        const accounts = await this.orm.searchRead("account.account", baseCompanyDom,
            ["id", "name", "code", "group_id"]);

        // 3) Líneas de movimiento (posted) en rango
        const moveLineDomain = [
            ["move_id.state", "=", "posted"],
            ["date", ">=", this.state.fromDate],
            ["date", "<=", this.state.toDate],
            ...baseCompanyDom,
            ...baseBranchDom,
        ];
        const moveLines = await this.orm.searchRead("account.move.line", moveLineDomain, [
            "id", "account_id", "date", "journal_id", "ref", "move_id", "move_name", "name", "debit", "credit",
        ]);

        // === Leer journals para armar "tipo - nombre" =====================
        const journalIds = [...new Set(moveLines
            .map(ml => (ml.journal_id && ml.journal_id[0]) || null)
            .filter(Boolean))];

        let journalMap = {};
        if (journalIds.length) {
            const journals = await this.orm.read("account.journal", journalIds, ["name", "type"]);
            journalMap = Object.fromEntries(journals.map(j => [j.id, j]));
        }

        const JOURNAL_TYPE_LABELS = {
            sale: "venta",
            purchase: "compra",
            cash: "efectivo",
            bank: "banco",
            general: "varios",
            // según configuración/extra módulos:
            sale_refund: "venta (NC)",
            purchase_refund: "compra (NC)",
        };

        for (const ml of moveLines) {
            const jId = ml.journal_id && ml.journal_id[0];
            const j = jId ? journalMap[jId] : null;
            const typeCode = j?.type || "";
            const typeLabel = JOURNAL_TYPE_LABELS[typeCode] || typeCode || "";
            const name = j?.name || (ml.journal_id && ml.journal_id[1]) || "";
            ml._journal_display = typeLabel ? `${typeLabel} - ${name}` : name;
        }

        // --- Mapas y acumulados
        const groupMap = {};
        for (const g of groups) {
            g.children = [];
            g.accounts = [];
            g.initial_balance_total = 0;
            g.debit_total = 0;
            g.credit_total = 0;
            g.ending_balance_total = 0;
            groupMap[g.id] = g;
        }

        const linesByAccount = {};
        for (const ml of moveLines) {
            const accId = ml.account_id && ml.account_id[0];
            if (!accId) continue;
            (linesByAccount[accId] ||= []).push(ml);
        }

        // Nota: saldo inicial aproximado con movimientos previos al primer día del mes del "fromDate"
        const from = new Date(fromDate);
        const monthStart = new Date(from.getFullYear(), from.getMonth(), 1);

        for (const acc of accounts) {
            const gid = acc.group_id && acc.group_id[0];
            if (!gid || !groupMap[gid]) continue;

            const lines = (linesByAccount[acc.id] || []).sort((a, b) => a.date.localeCompare(b.date));
            let debit = 0, credit = 0, initial_balance = 0;

            for (const l of lines) {
                const d = new Date(l.date);
                if (d < monthStart) {
                    initial_balance += (l.debit || 0) - (l.credit || 0);
                } else {
                    debit += l.debit || 0;
                    credit += l.credit || 0;
                }
            }
            acc.initial_balance = initial_balance;
            acc.debit = debit;
            acc.credit = credit;
            acc.ending_balance = initial_balance + debit - credit;
            acc.lines = lines;

            groupMap[gid].accounts.push(acc);
        }

        // Jerarquía grupo → hijos
        const roots = [];
        for (const g of groups) {
            const pid = g.group_id && g.group_id[0];
            if (pid && groupMap[pid]) groupMap[pid].children.push(g);
            else roots.push(g);
        }

        function computeTotals(g) {
            let ib = 0, db = 0, cr = 0, eb = 0;
            for (const a of g.accounts) {
                ib += a.initial_balance || 0;
                db += a.debit || 0;
                cr += a.credit || 0;
                eb += a.ending_balance || 0;
            }
            for (const c of g.children) {
                computeTotals(c);
                ib += c.initial_balance_total || 0;
                db += c.debit_total || 0;
                cr += c.credit_total || 0;
                eb += c.ending_balance_total || 0;
            }
            g.initial_balance_total = ib;
            g.debit_total = db;
            g.credit_total = cr;
            g.ending_balance_total = eb;
        }

        const parseCode = (code) => (code || "").split(".").map(s => isFinite(+s) ? +s : 0);
        const cmpCodes = (a, b) => {
            const A = parseCode(a), B = parseCode(b);
            const n = Math.max(A.length, B.length);
            for (let i = 0; i < n; i++) {
                const x = A[i] || 0, y = B[i] || 0;
                if (x !== y) return x - y;
            }
            return String(a || "").localeCompare(String(b || ""));
        };

        function hasPeriodMovement(acc) {
            const hasLines = (acc.lines?.length || 0) > 0;
            const hasDrCr = (acc.debit || 0) !== 0 || (acc.credit || 0) !== 0;
            //? const hasOpening = (acc.initial_balance || 0) !== 0; //->SOLO SI se requiere cuenta con saldo inicial pero sin movimientos
            return hasLines || hasDrCr;
        }

        function pruneGroup(g) {
            g.accounts = g.accounts.filter(acc => includeEmpty || hasPeriodMovement(acc));
            g.children = g.children.filter(ch => pruneGroup(ch));
            return (g.accounts.length > 0) || (g.children.length > 0);
        }

        if (!includeEmpty) {
            for (let i = roots.length - 1; i >= 0; i--) {
                if (!pruneGroup(roots[i])) {
                    roots.splice(i, 1);
                }
            }
        }

        function buildItems(g) {
            g.accounts.sort((a, b) => {
                const by = cmpCodes(a.code, b.code);
                return by !== 0 ? by : String(a.name || "").localeCompare(String(b.name || ""));
            });
            g.children.sort((a, b) => {
                const by = cmpCodes(a.code_prefix_start, b.code_prefix_start);
                return by !== 0 ? by : String(a.name || "").localeCompare(String(b.name || ""));
            });
            g.items = [
                ...g.accounts.map(a => ({kind: "acc", id: a.id, code: a.code, ref: a})),
                ...g.children.map(c => ({kind: "grp", id: c.id, code: c.code_prefix_start, ref: c})),
            ];
            for (const c of g.children) buildItems(c);
        }

        for (const r of roots) {
            buildItems(r);
            computeTotals(r);
        }

        const parentByPath = new Map();

        function annotate(g, parentPath = null, level = 0) {
            g.level = level;
            g.path = parentPath ? `${parentPath}-${g.id}` : `g-${g.id}`;
            g.parentPath = parentPath || null;
            if (parentPath) parentByPath.set(g.path, parentPath);

            for (const a of g.accounts) {
                a.level = level + 1;
                a.parentPath = g.path;
                a.path = `a-${a.id}`;
                parentByPath.set(a.path, a.parentPath);

                for (const ln of (a.lines || [])) {
                    ln.level = a.level + 1;
                    ln.parentPath = a.path;
                    ln.path = `l-${ln.id}`;
                    parentByPath.set(ln.path, ln.parentPath);
                }
            }
            for (const c of g.children) annotate(c, g.path, level + 1);
        }

        for (const r of roots) annotate(r);

        this.state.groups = includeEmpty ? roots : roots.filter(g => (g.items?.length || 0) > 0);
        this.state.parentByPath = parentByPath;
    }
}

class KualeAuxMovementRenderer extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            collapsed: {},
            companyList: [],
            selectedCompanyId: null,
            branchList: [],
            selectedBranchId: null,
            satNivelList: [
                {value: "", label: "Todos"},
                {value: "1", label: "1. ESTADO DE SITUACIÓN FINANCIERA"},
                {value: "2", label: "2. ESTADO DE RESULTADOS"},
                {value: "3", label: "3. ESTADO DE OTROS RESULTADOS INTEGRALES"},
                {value: "4", label: "4. CUENTAS DE ORDEN"},
                {value: "5", label: "5. ESTADO DE FLUJOS DE EFECTIVO"},
            ],
            selectedSatNivel: null,
            includeEmpty: true,
            fromDate: this.getStartOfMonth(),
            toDate: this.getToday(),
            codeFrom: "",
            codeTo: "",
        });

        onWillStart(async () => {
            await loadJS("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.17.2/xlsx.full.min.js");
            const companies = await this.orm.searchRead("res.company", [["parent_id", "=", false]], ["id", "name"]);
            this.state.companyList = companies;
            if (companies.length) {
                this.state.selectedCompanyId = companies[0].id;
                await this.loadBranches();
                await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, this.state.selectedSatNivel, this.state.includeEmpty);
            }
        });
    }

    onToggle(ev) {
        const tr = ev.currentTarget;
        if (!tr.classList.contains("toggle")) return;
        const root = tr.closest("tbody") || tr.closest("table") || this.el;

        let icon = tr.querySelector(".k-toggle-icon");
        if (!icon) {
            const firstSpan = tr.querySelector("td span") || tr.querySelector("td");
            icon = document.createElement("span");
            icon.className = "k-toggle-icon";
            icon.textContent = "[+]";
            if (firstSpan) {
                firstSpan.insertBefore(icon, firstSpan.firstChild);
                firstSpan.insertBefore(document.createTextNode(" "), icon.nextSibling);
            }
        }

        const id = tr.getAttribute("data-id");
        const isExpanded = icon.textContent.includes("[-]");
        if (isExpanded) {
            icon.textContent = "[+]";
            this.hideDescendants(id, root);
        } else {
            icon.textContent = "[-]";
            this.showDirectChildren(id, root);
        }
    }

    showDirectChildren(parentId, rootEl) {
        const root = rootEl || this.el || document;
        root.querySelectorAll(`tr.child-row.parent-${CSS.escape(parentId)}`).forEach(el => el.style.display = "table-row");
    }

    hideDescendants(parentId, rootEl) {
        const root = rootEl || this.el || document;
        root.querySelectorAll(`tr.child-row.parent-${CSS.escape(parentId)}`).forEach((child) => {
            child.style.display = "none";
            if (child.classList.contains("toggle")) {
                const icon = child.querySelector(".k-toggle-icon");
                if (icon) icon.textContent = "[+]";
                const cid = child.getAttribute("data-id");
                if (cid) this.hideDescendants(cid, root);
            }
        });
    }

    async onCompanyChange(ev) {
        this.state.selectedCompanyId = parseInt(ev.target.value);
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedSatNivel, this.state.includeEmpty,
            this.state.fromDate, this.state.toDate,
            this.state.codeFrom, this.state.codeTo);
        this.state.collapsed = {};
    }

    getStartOfMonth() {
        const d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().split("T")[0];
    }

    getToday() {
        return new Date().toISOString().split("T")[0];
    }

    async loadBranches() {
        if (!this.state.selectedCompanyId) {
            this.state.branchList = [];
            this.state.selectedBranchId = null;
            return;
        }

        const branches = await this.orm.searchRead(
            "res.company",
            [["parent_id", "=", this.state.selectedCompanyId]],
            ["id", "name"]
        );

        this.state.branchList = [{id: null, name: "Todas las sucursales"}, ...branches];
        this.state.selectedBranchId = this.state.branchList.length > 1 ? this.state.branchList[0].id : null;
    }

    async onCompanyChange(ev) {
        this.state.selectedCompanyId = parseInt(ev.target.value);
        await this.loadBranches();
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, this.state.selectedSatNivel, this.state.includeEmpty,
            this.state.fromDate, this.state.toDate, this.state.codeFrom, this.state.codeTo);
        this.state.collapsed = {};
    }

    async onBranchChange(ev) {
        this.state.selectedBranchId = ev.target.value === "null" ? null : parseInt(ev.target.value);
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, this.state.selectedSatNivel, this.state.includeEmpty,
            this.state.fromDate, this.state.toDate, this.state.codeFrom, this.state.codeTo);
        this.state.collapsed = {};
    }

    async onSatNivelChange(ev) {
        const satNivel = ev.target.value || null;
        this.state.selectedSatNivel = satNivel;
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, satNivel, this.state.includeEmpty,
            this.state.fromDate, this.state.toDate, this.state.codeFrom, this.state.codeTo);
        this.state.collapsed = {};
    }

    async onIncludeEmptyToggle(ev) {
        this.state.includeEmpty = !!ev.target.checked;
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, this.state.selectedSatNivel, this.state.includeEmpty,
            this.state.fromDate, this.state.toDate, this.state.codeFrom, this.state.codeTo);
        this.state.collapsed = {};
    }

    async onDateChange() {
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, this.state.selectedSatNivel, this.state.includeEmpty,
            this.state.fromDate, this.state.toDate, this.state.codeFrom, this.state.codeTo);
    }

    async onCodeRangeChange() {
        await this.props.model.load(
            this.state.selectedCompanyId, this.state.selectedBranchId, this.state.selectedSatNivel, this.state.includeEmpty,
            this.state.fromDate, this.state.toDate, this.state.codeFrom?.trim(), this.state.codeTo?.trim()
        );
    }

    async exportToExcel() {
        const wb = XLSX.utils.book_new();

        // ===== Hoja 1: Filtros / encabezado =====
        const companyName =
            (this.state.companyList.find(c => c.id === this.state.selectedCompanyId) || {}).name || "";

        const filters = [
            ["Compañía", companyName],
            ["Desde", this.state.fromDate],
            ["Hasta", this.state.toDate],
            ["Nivel SAT", this.state.selectedSatNivel || "Todos"],
            ["Incluir vacíos", this.state.includeEmpty ? "Sí" : "No"],
            ["Código desde", this.state.codeFrom || "—"],
            ["Código hasta", this.state.codeTo || "—"],
            ["Generado", new Date().toISOString()],
        ];
        const wsFilters = XLSX.utils.aoa_to_sheet(filters);
        XLSX.utils.book_append_sheet(wb, wsFilters, "Filtros");

        // ===== Hoja 2: Movimientos =====
        const header = [
            "Tipo",            // Grupo / Cuenta / Movimiento
            "Código",
            "Fecha",
            "Nombre",
            "Tipo (Journal)",
            "Referencia",
            "Saldo Inicial",
            "Débito",
            "Crédito",
            "Balance",
            "Nivel",
            "Ruta",
        ];
        const rows = [header];

        const groups = this.props.model.state.groups || [];

        const num = v => Number((v || 0).toFixed(2));

        const pushAccount = (a) => {
            // Cuenta
            rows.push([
                "Cuenta",
                a.code || "",
                "",
                a.name || "",
                "",
                "",
                num(a.initial_balance),
                num(a.debit),
                num(a.credit),
                num(a.ending_balance),
                a.level ?? "",
                a.path || `a-${a.id}`,
            ]);

            // Líneas de la cuenta
            for (const ln of (a.lines || [])) {
                rows.push([
                    "Movimiento",
                    "",
                    ln.date || "",
                    ln.name || ln.move_name || "Línea",
                    ln._journal_display || "",
                    ln.ref || "",
                    "",                                // SI (no aplica a línea)
                    num(ln.debit),
                    num(ln.credit),
                    num((ln.debit || 0) - (ln.credit || 0)),
                    (a.level ?? 0) + 1,
                    ln.path || `l-${ln.id}`,
                ]);
            }
        };

        const pushGroup = (g) => {
            // Grupo
            rows.push([
                "Grupo",
                g.code_prefix_start || "",
                "",
                g.name || "",
                "",
                "",
                num(g.initial_balance_total),
                num(g.debit_total),
                num(g.credit_total),
                num(g.ending_balance_total),
                g.level ?? 0,
                g.path || `g-${g.id}`,
            ]);

            // Cuentas primero (ya ordenadas en items)
            for (const it of (g.items || [])) {
                if (it.kind === "acc") pushAccount(it.ref);
            }
            // Luego subgrupos
            for (const it of (g.items || [])) {
                if (it.kind === "grp") pushGroup(it.ref);
            }
        };

        for (const r of groups) pushGroup(r);

        const ws = XLSX.utils.aoa_to_sheet(rows);

        // Anchos
        ws["!cols"] = [
            {wch: 12}, // Tipo
            {wch: 16}, // Código
            {wch: 12}, // Fecha
            {wch: 48}, // Nombre
            {wch: 28}, // Tipo (Journal)
            {wch: 24}, // Referencia
            {wch: 16}, // SI
            {wch: 16}, // Débito
            {wch: 16}, // Crédito
            {wch: 16}, // Balance
            {wch: 8},  // Nivel
            {wch: 24}, // Ruta
        ];

        // Formato numérico para montos (cols 6..9 => índices 6,7,8,9)
        const range = XLSX.utils.decode_range(ws["!ref"]);
        for (let R = 1; R <= range.e.r; R++) {
            for (const C of [6, 7, 8, 9]) {
                const cell = ws[XLSX.utils.encode_cell({r: R, c: C})];
                if (cell && typeof cell.v === "number") {
                    cell.t = "n";
                    cell.z = "#,##0.00";
                }
            }
        }

        XLSX.utils.book_append_sheet(wb, ws, "Movimientos");

        const safeCompany = (companyName || "compania").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 40);
        const codeRange =
            (this.state.codeFrom ? `_${this.state.codeFrom}` : "") +
            (this.state.codeTo ? `-${this.state.codeTo}` : "");
        const fname = `mov_aux_${safeCompany}_${this.state.fromDate}_${this.state.toDate}${codeRange}.xlsx`;

        XLSX.writeFile(wb, fname);
    }

    async exportToPDF() {
        try {
            const generator = new PDFReportGenerator();
            const companyName = (this.state.companyList.find(c => c.id === this.state.selectedCompanyId) || {}).name || "";

            // Corregir la lógica para obtener el nombre de la sucursal
            let branchName = 'Todas las sucursales';
            if (this.state.selectedBranchId && this.state.selectedBranchId !== "") {
                // Convertir ambos valores a string para comparación consistente
                const selectedBranch = this.state.branchList.find(b => String(b.id) === String(this.state.selectedBranchId));
                branchName = selectedBranch ? selectedBranch.name : 'Sucursal no encontrada';
                console.log('Selected branch ID:', this.state.selectedBranchId, 'Found branch:', selectedBranch);
            } else {
                // Si selectedBranchId es null, undefined o "", buscar "Todas las sucursales"
                const allBranches = this.state.branchList.find(b => b.id === "" || b.name === "Todas las sucursales");
                branchName = allBranches ? allBranches.name : 'Todas las sucursales';
            }

            const reportData = {
                title: "Movimientos Auxiliares",
                company: companyName,
                branch: branchName,
                fromDate: this.state.fromDate,
                toDate: this.state.toDate,
                satNivel: this.state.selectedSatNivel
                    ? (this.state.satNivelList.find(s => s.value === this.state.selectedSatNivel) || {}).label || ""
                    : "Todos",
                includeEmpty: this.state.includeEmpty ? "Sí" : "No",
                codeFrom: this.state.codeFrom || "—",
                codeTo: this.state.codeTo || "—",
                rows: this.prepareAuxMovementsRows()
            };

            await generator.generatePDF(reportData);
        } catch (error) {
            console.error("Error al exportar PDF:", error);
            alert("Error al generar el PDF. Por favor, inténtelo nuevamente.");
        }
    }

    prepareAuxMovementsRows() {
        const rows = [];

        const processGroup = (group, level = 0) => {
            // Agregar fila del grupo
            rows.push({
                type: 'group',
                name: group.name || '',
                code: group.code_prefix_start || '',
                date: '',
                journalType: '',
                reference: '',
                initialBalance: group.initial_balance_total || 0,
                debit: group.debit_total || 0,
                credit: group.credit_total || 0,
                balance: group.ending_balance_total || 0,
                level: level,
                path: group.path || `g-${group.id}`
            });

            // Procesar elementos del grupo (cuentas y subgrupos)
            for (const item of group.items || []) {
                if (item.kind === 'acc') {
                    const account = item.ref;
                    // Agregar fila de la cuenta
                    rows.push({
                        type: 'account',
                        name: account.name || '',
                        code: account.code || '',
                        date: '',
                        journalType: '',
                        reference: '',
                        initialBalance: account.initial_balance || 0,
                        debit: account.debit || 0,
                        credit: account.credit || 0,
                        balance: account.ending_balance || 0,
                        level: level + 1,
                        path: account.path || `a-${account.id}`
                    });

                    // Procesar líneas de movimiento de la cuenta
                    for (const line of account.lines || []) {
                        rows.push({
                            type: 'movement',
                            name: line.name || line.move_name || 'Línea',
                            code: '',
                            date: line.date || '',
                            journalType: line._journal_display || '',
                            reference: line.ref || '',
                            initialBalance: 0,
                            debit: line.debit || 0,
                            credit: line.credit || 0,
                            balance: (line.debit || 0) - (line.credit || 0),
                            level: level + 2,
                            path: line.path || `l-${line.id}`
                        });
                    }
                } else if (item.kind === 'grp') {
                    // Procesar subgrupo recursivamente
                    processGroup(item.ref, level + 1);
                }
            }
        };

        // Procesar todos los grupos raíz
        for (const group of this.props.model.state.groups || []) {
            processGroup(group);
        }

        return rows;
    }
}

KualeAuxMovementRenderer.template = "kuale_aux_movement.Renderer";

class KualeAuxMovementController extends Component {
    setup() {
        this.orm = useService("orm");
        this.model = useState(new this.props.Model(this.orm));
        this.display = {controlPanel: true};
    }
}

KualeAuxMovementController.template = "kuale_aux_movement.View";
KualeAuxMovementController.components = {Layout};

export const kualeAuxMovementView = {
    type: "kuale_aux_movement",
    display_name: "Kuale Auxiliary Movement",
    icon: "fa fa-table",
    multiRecord: true,
    Controller: KualeAuxMovementController,
    Model: KualeAuxMovementModel,
    Renderer: KualeAuxMovementRenderer,
    props() {
        return {Model: KualeAuxMovementModel, Renderer: KualeAuxMovementRenderer};
    },
};
registry.category("views").add("kuale_aux_movement", kualeAuxMovementView);