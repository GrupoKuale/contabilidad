/** @odoo-module **/

import {Layout} from "@web/search/layout";
import {useService} from "@web/core/utils/hooks";
import {Component, onWillStart, useState, onMounted} from "@odoo/owl";
import {KeepLast} from "@web/core/utils/concurrency";
import {registry} from "@web/core/registry";

import {loadJS, loadCSS} from "@web/core/assets";
import {PDFReportGenerator} from "../js/pdf_generator";

class KualeTrialBalanceModel {
    constructor(orm, resModel, fields, archInfo, domain) {
        this.orm = orm;
        this.resModel = resModel;
        this.keeplast = new KeepLast();
        this.state = useState({
            groups: [],
            parentByPath: new Map(),
            fromDate: this.getStartOfMonth(),
            toDate: this.getToday(),
        });
    }

    getStartOfMonth() {
        const today = new Date();
        return new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
    }

    getToday() {
        const today = new Date();
        return today.toISOString().split('T')[0];
    }

    /**
     * @param {number|null} company_id
     * @param {number|null} branch_id
     * @param {string|null} sat_nivel
     * @param {boolean} includeEmpty
     * @param {string} fromDate
     * @param {string} toDate
     */
    async load(
        company_id = null,
        branch_id = null,
        sat_nivel = null,
        includeEmpty = true,
        fromDate = this.state.fromDate,
        toDate = this.state.toDate
    ) {
        this.state.fromDate = fromDate;
        this.state.toDate = toDate;

        const baseCompanyDom = company_id ? [["company_id", "=", company_id]] : [];
        const groupDomain = [...baseCompanyDom];
        if (sat_nivel) groupDomain.push(["sat_nivel", "=", sat_nivel]);

        // 1) Grupos
        const groups = await this.orm.searchRead("account.group", groupDomain, [
            "id", "name", "group_id", "code_prefix_start", "sat_nivel",
        ]);

        // 2) Cuentas
        const accounts = await this.orm.searchRead("account.account", baseCompanyDom, [
            "id", "name", "code", "group_id",
        ]);

        // 3) Movimientos (posted) DENTRO del rango seleccionado - con filtro de sucursal
        const moveLineDomain = [
            ["move_id.state", "=", "posted"],
            ["date", ">=", this.state.fromDate],
            ["date", "<=", this.state.toDate],
            ...baseCompanyDom,
        ];

        // Agregar filtro de sucursal si está seleccionada
        if (branch_id) {
            moveLineDomain.push(["move_id.branch_id", "=", parseInt(branch_id)]);
        }
        const moveLines = await this.orm.searchRead("account.move.line", moveLineDomain, [
            "account_id", "debit", "credit", "date",
        ]);

        // --- Preparativos
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

        // Indexar líneas (SOLO del periodo)
        const linesByAccount = {};
        for (const ml of moveLines) {
            const accId = ml.account_id?.[0];
            if (!accId) continue;
            (linesByAccount[accId] ||= []).push(ml);
        }

        // Calcular saldos por cuenta
        const from = new Date(fromDate);
        const monthStart = new Date(from.getFullYear(), from.getMonth(), 1); // alineado a Aux

        for (const acc of accounts) {
            const gid = acc.group_id?.[0];
            if (!gid || !groupMap[gid]) continue;

            const lines = (linesByAccount[acc.id] || []).sort((a, b) => a.date.localeCompare(b.date));
            let debit = 0, credit = 0, initial_balance = 0;

            // Nota: con el dominio actual solo traemos >= fromDate; este “initial” queda normalmente en 0.
            // Se deja igual que Aux para consistencia; si luego quieres SI real, habría que consultar previas.
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
            acc._period_lines_count = lines.length; // para onIncludeEmpty
            groupMap[gid].accounts.push(acc);
        }

        // Armar jerarquía
        const roots = [];
        for (const g of groups) {
            const pid = g.group_id?.[0];
            if (pid && groupMap[pid]) groupMap[pid].children.push(g);
            else roots.push(g);
        }

        // === onIncludeEmpty: filtrar cuentas/grupos sin movimientos (igual lógica que Aux) ===
        const hasPeriodMovement = (acc) => {
            const hasLines = (acc._period_lines_count || 0) > 0;
            const hasDrCr = (acc.debit || 0) !== 0 || (acc.credit || 0) !== 0;
            // Si quisieras considerar saldo inicial!=0 como “mostrar”, descomenta:
            // const hasOpening = (acc.initial_balance || 0) !== 0;
            return hasLines || hasDrCr; // || hasOpening;
        };

        function pruneGroup(g) {
            // filtra cuentas
            g.accounts = g.accounts.filter(acc => includeEmpty || hasPeriodMovement(acc));
            // filtra hijos recursivamente
            g.children = g.children.filter(ch => pruneGroup(ch));
            // mantener grupo solo si tiene algo
            return (g.accounts.length > 0) || (g.children.length > 0);
        }

        if (!includeEmpty) {
            for (let i = roots.length - 1; i >= 0; i--) {
                if (!pruneGroup(roots[i])) roots.splice(i, 1);
            }
        }

        // Totales por grupo
        function computeTotals(g) {
            let ib = 0, db = 0, cr = 0, eb = 0;
            for (const acc of g.accounts) {
                ib += acc.initial_balance || 0;
                db += acc.debit || 0;
                cr += acc.credit || 0;
                eb += acc.ending_balance || 0;
            }
            for (const ch of g.children) {
                computeTotals(ch);
                ib += ch.initial_balance_total || 0;
                db += ch.debit_total || 0;
                cr += ch.credit_total || 0;
                eb += ch.ending_balance_total || 0;
            }
            g.initial_balance_total = ib;
            g.debit_total = db;
            g.credit_total = cr;
            g.ending_balance_total = eb;
        }

        // helpers para orden
        function parseCode(code) {
            if (!code) return [];
            return String(code).split(".").map(s => {
                const n = parseInt(s, 10);
                return Number.isFinite(n) ? n : 0;
            });
        }
        function cmpCodes(a, b) {
            const A = parseCode(a), B = parseCode(b);
            const n = Math.max(A.length, B.length);
            for (let i = 0; i < n; i++) {
                const x = A[i] || 0, y = B[i] || 0;
                if (x !== y) return x - y;
            }
            return String(a || "").localeCompare(String(b || ""));
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
                ...g.accounts.map(acc => ({kind: "acc", id: acc.id, code: acc.code, ref: acc})),
                ...g.children.map(ch => ({kind: "grp", id: ch.id, code: ch.code_prefix_start, ref: ch})),
            ];
            for (const ch of g.children) buildItems(ch);
        }

        for (const r of roots) {
            buildItems(r);
            computeTotals(r);
        }

        // Anotar path / parentPath / level
        const parentByPath = new Map();
        function annotate(g, parentPath = null, level = 0) {
            g.level = level;
            g.path = parentPath ? `${parentPath}-${g.id}` : `g-${g.id}`;
            g.parentPath = parentPath || null;
            if (parentPath) parentByPath.set(g.path, parentPath);

            for (const acc of g.accounts) {
                acc.level = level + 1;
                acc.parentPath = g.path;
                acc.path = `a-${acc.id}`;
                parentByPath.set(acc.path, acc.parentPath);
            }
            for (const ch of g.children) annotate(ch, g.path, level + 1);
        }
        for (const r of roots) annotate(r);

        this.state.groups = roots;
        this.state.parentByPath = parentByPath;
    }
}

class KualeTrialBalanceRenderer extends Component {
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
        });

        onWillStart(async () => {
            console.log("onWillStart - Loading companies");
            await loadJS("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.17.2/xlsx.full.min.js");
            // Cambiar consulta para buscar compañías principales (sin parent_id)
            const companies = await this.orm.searchRead("res.company", [["parent_id", "=", false]], ["id", "name"]);
            console.log("Companies loaded:", companies);
            this.state.companyList = companies;
            if (companies.length > 0) {
                this.state.selectedCompanyId = companies[0].id;
                console.log("Selected company ID:", this.state.selectedCompanyId);
                await this.loadBranches(companies[0].id);
                await this.props.model.load(
                    this.state.selectedCompanyId,
                    this.state.selectedBranchId,
                    this.state.selectedSatNivel,
                    this.state.includeEmpty
                );
            }
        });
    }

    /* Toggle expand/collapse */
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
        root.querySelectorAll(`tr.child-row.parent-${CSS.escape(parentId)}`).forEach((child) => {
            child.style.display = "table-row";
        });
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

    /* Métodos auxiliares */
    async loadBranches(companyId) {
        console.log("loadBranches called with companyId:", companyId);
        if (!companyId) {
            this.state.branchList = [];
            this.state.selectedBranchId = null;
            console.log("No companyId, clearing branches");
            return;
        }

        // Cargar sucursales de la compañía seleccionada
        const branches = await this.orm.searchRead("res.company", [["parent_id", "=", companyId]], ["id", "name"]);
        console.log("Branches found:", branches);

        // Si no hay sucursales, incluir la compañía principal
        if (branches.length === 0) {
            const parentCompany = await this.orm.searchRead("res.company", [["id", "=", companyId]], ["id", "name"]);
            this.state.branchList = [{id: "", name: "Todas las sucursales"}, ...parentCompany];
            console.log("No branches, using parent company:", this.state.branchList);
        } else {
            this.state.branchList = [{id: "", name: "Todas las sucursales"}, ...branches];
            console.log("Branches loaded:", this.state.branchList);
        }

        this.state.selectedBranchId = this.state.branchList.length > 1 ? this.state.branchList[0].id : null;
        console.log("Selected branch ID:", this.state.selectedBranchId);
    }

    /* Filtros */
    async onCompanyChange(ev) {
        const companyId = parseInt(ev.target.value);
        this.state.selectedCompanyId = companyId;
        await this.loadBranches(companyId);
        await this.props.model.load(companyId, this.state.selectedBranchId, this.state.selectedSatNivel, this.state.includeEmpty, this.state.fromDate, this.state.toDate);
        this.state.collapsed = {};
    }

    async onBranchChange(ev) {
        const branchId = ev.target.value || null;
        this.state.selectedBranchId = branchId;
        await this.props.model.load(this.state.selectedCompanyId, branchId, this.state.selectedSatNivel, this.state.includeEmpty, this.state.fromDate, this.state.toDate);
        this.state.collapsed = {};
    }

    async onSatNivelChange(ev) {
        const satNivel = ev.target.value || null;
        this.state.selectedSatNivel = satNivel;
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, satNivel, this.state.includeEmpty, this.state.fromDate, this.state.toDate);
        this.state.collapsed = {};
    }

    async onIncludeEmptyToggle(ev) {
        this.state.includeEmpty = !!ev.target.checked;
        await this.props.model.load(
            this.state.selectedCompanyId,
            this.state.selectedBranchId,
            this.state.selectedSatNivel,
            this.state.includeEmpty,
            this.state.fromDate,
            this.state.toDate
        );
        this.state.collapsed = {};
    }

    getStartOfMonth() {
        const today = new Date();
        return new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
    }

    getToday() {
        const today = new Date();
        return today.toISOString().split('T')[0];
    }

    async onDateChange() {
        await this.props.model.load(
            this.state.selectedCompanyId,
            this.state.selectedBranchId,
            this.state.selectedSatNivel,
            this.state.includeEmpty,
            this.state.fromDate,
            this.state.toDate
        );
    }

    async exportToExcel() {
        console.log("exportToExcel");
        const wb = XLSX.utils.book_new();

        // === Hoja 1: Filtros/encabezado ===
        const companyName = (this.state.companyList.find(c => c.id === this.state.selectedCompanyId) || {}).name || "";
        const filters = [
            ["Compañía", companyName],
            ["Desde", this.state.fromDate],
            ["Hasta", this.state.toDate],
            ["Nivel SAT", this.state.selectedSatNivel || "Todos"],
            ["Incluir vacíos", this.state.includeEmpty ? "Sí" : "No"],
            ["Generado", new Date().toISOString()],
        ];
        const wsFilters = XLSX.utils.aoa_to_sheet(filters);
        XLSX.utils.book_append_sheet(wb, wsFilters, "Filtros");

        // === Hoja 2: Balanza detallada ===
        const header = [
            "Tipo",
            "Nombre",
            "Código",
            "Saldo Inicial",
            "Débito",
            "Crédito",
            "Saldo Final",
            "Nivel",
            "Ruta"
        ];

        const rows = [header];

        const pushGroup = (g) => {
            rows.push([
                "Grupo",
                g.name || "",
                g.code_prefix_start || "",
                Number((g.initial_balance_total || 0).toFixed(2)),
                Number((g.debit_total || 0).toFixed(2)),
                Number((g.credit_total || 0).toFixed(2)),
                Number((g.ending_balance_total || 0).toFixed(2)),
                g.level ?? 0,
                g.path || `g-${g.id}`,
            ]);

            for (const it of (g.items || [])) {
                if (it.kind === "acc") {
                    const a = it.ref;
                    rows.push([
                        "Cuenta",
                        a.name || "",
                        a.code || "",
                        Number((a.initial_balance || 0).toFixed(2)),
                        Number((a.debit || 0).toFixed(2)),
                        Number((a.credit || 0).toFixed(2)),
                        Number((a.ending_balance || 0).toFixed(2)),
                        (g.level ?? 0) + 1,
                        a.path || `a-${a.id}`,
                    ]);
                }
            }
            for (const it of (g.items || [])) {
                if (it.kind === "grp") pushGroup(it.ref);
            }
        };

        for (const r of (this.props.model.state.groups || [])) {
            pushGroup(r);
        }

        const ws = XLSX.utils.aoa_to_sheet(rows);

        ws['!cols'] = [
            {wch: 10},
            {wch: 48},
            {wch: 16},
            {wch: 16},
            {wch: 16},
            {wch: 16},
            {wch: 16},
            {wch: 8},
            {wch: 24},
        ];

        const range = XLSX.utils.decode_range(ws['!ref']);
        for (let R = 1; R <= range.e.r; R++) {
            for (let C of [3, 4, 5, 6]) {
                const cell = ws[XLSX.utils.encode_cell({r: R, c: C})];
                if (cell && typeof cell.v === "number") {
                    cell.t = "n";
                    cell.z = "#,##0.00";
                }
            }
        }

        XLSX.utils.book_append_sheet(wb, ws, "Balanza");

        const safeCompany = companyName.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 40) || "compania";
        const fname = `balanza_${safeCompany}_${this.state.fromDate}_${this.state.toDate}.xlsx`;
        XLSX.writeFile(wb, fname);
    }

    async exportToPDF() {
        console.log("exportToPDF");
        try {
            const pdfGenerator = new PDFReportGenerator();

            const companyName = (this.state.companyList.find(c => c.id === this.state.selectedCompanyId) || {}).name || 'Sin especificar';

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
                title: 'Plan de Cuentas (Balanza de Comprobación)',
                company: companyName,
                branch: branchName,
                fromDate: this.state.fromDate,
                toDate: this.state.toDate,
                satNivel: this.state.selectedSatNivel
                    ? (this.state.satNivelList.find(s => s.value === this.state.selectedSatNivel) || {}).label || ""
                    : "Todos",
                includeEmpty: this.state.includeEmpty ? "Sí" : "No",
                rows: this.prepareTrialBalanceRows()
            };

            const safeCompany = companyName.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 40) || "compania";
            const filename = `plan_cuentas_${safeCompany}_${this.state.fromDate}_${this.state.toDate}.pdf`;

            await pdfGenerator.generatePDF(reportData, filename);
        } catch (error) {
            console.error('Error generating PDF:', error);
            alert('Error al generar el PDF: ' + error.message);
        }
    }

    prepareTrialBalanceRows() {
        const rows = [];

        const processGroup = (group, level = 0) => {
            // Agregar fila del grupo
            rows.push({
                type: 'group',
                name: group.name || '',
                code: group.code_prefix_start || '',
                initialBalance: group.initial_balance_total || 0,
                debit: group.debit_total || 0,
                credit: group.credit_total || 0,
                endingBalance: group.ending_balance_total || 0,
                level: level,
                path: group.path || `g-${group.id}`
            });

            // Procesar cuentas del grupo
            for (const account of group.accounts || []) {
                rows.push({
                    type: 'account',
                    name: account.name || '',
                    code: account.code || '',
                    initialBalance: account.initial_balance || 0,
                    debit: account.debit || 0,
                    credit: account.credit || 0,
                    endingBalance: account.ending_balance || 0,
                    level: level + 1,
                    path: account.path || `a-${account.id}`
                });
            }

            // Procesar subgrupos recursivamente
            for (const child of group.children || []) {
                processGroup(child, level + 1);
            }
        };

        // Procesar todos los grupos raíz
        for (const group of this.props.model.state.groups || []) {
            processGroup(group);
        }

        return rows;
    }
}

KualeTrialBalanceRenderer.template = "kuale_trial_balance.Renderer";

class KualeTrialBalanceController extends Component {
    setup() {
        this.orm = useService("orm");
        this.model = useState(new this.props.Model(this.orm));
        this.display = {controlPanel: true};
    }
}

KualeTrialBalanceController.template = "kuale_trial_balance.View";
KualeTrialBalanceController.components = {Layout};

export const kualeTrialBalanceView = {
    type: "kuale_trial_balance",
    display_name: "Kuale Trial Balance",
    icon: "fa fa-table",
    multiRecord: true,
    Controller: KualeTrialBalanceController,
    Model: KualeTrialBalanceModel,
    Renderer: KualeTrialBalanceRenderer,
    props() {
        return {Model: KualeTrialBalanceModel, Renderer: KualeTrialBalanceRenderer};
    },
};
registry.category("views").add("kuale_trial_balance", kualeTrialBalanceView);