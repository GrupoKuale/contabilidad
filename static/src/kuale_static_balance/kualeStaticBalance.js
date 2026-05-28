/** @odoo-module **/

import {Layout} from "@web/search/layout";
import {useService} from "@web/core/utils/hooks";
import {Component, onWillStart, useState, onMounted} from "@odoo/owl";
import {KeepLast} from "@web/core/utils/concurrency";
import {registry} from "@web/core/registry";

import {loadJS, loadCSS} from "@web/core/assets";
import {PDFReportGenerator} from "../js/pdf_generator";

class KualeStaticBalanceModel {
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
        const d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().split("T")[0]; // YYYY-MM-DD
    }

    getToday() {
        return new Date().toISOString().split("T")[0]; // YYYY-MM-DD
    }

    /**
     * @param {number|null} company_id
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
        const baseBranchDom = branch_id ? [["branch_id", "=", parseInt(branch_id)]] : [];
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

        // 3) Líneas de movimiento (posted) en rango
        const moveLineDomain = [
            ["move_id.state", "=", "posted"],
            ["date", ">=", this.state.fromDate],
            ["date", "<=", this.state.toDate],
            ...baseCompanyDom,
            ...baseBranchDom,
        ];
        const moveLines = await this.orm.searchRead("account.move.line", moveLineDomain, [
            "id", "account_id", "date", "debit", "credit",
        ]);

        // --- Preparar grupos
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

        // Indexar líneas por cuenta
        const linesByAccount = {};
        for (const ml of moveLines) {
            const accId = ml.account_id?.[0];
            if (!accId) continue;
            (linesByAccount[accId] ||= []).push(ml);
        }

        // Calcular saldos por cuenta y asignar al grupo
        // monthStart alineado a fromDate (no al mes "de hoy")
        const from = new Date(fromDate);
        const monthStart = new Date(from.getFullYear(), from.getMonth(), 1);

        for (const acc of accounts) {
            const gid = acc.group_id?.[0];
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
            acc._period_lines_count = lines.filter(l => new Date(l.date) >= monthStart).length; // para onIncludeEmpty

            groupMap[gid].accounts.push(acc);
        }

        // Jerarquía raíz / hijos
        const roots = [];
        for (const g of groups) {
            const pid = g.group_id?.[0];
            if (pid && groupMap[pid]) groupMap[pid].children.push(g);
            else roots.push(g);
        }

        // === OnIncludeEmpty: poda por movimiento del periodo (igual que Aux/TrialBalance) ===
        const hasPeriodMovement = (acc) => {
            const hasLines = (acc._period_lines_count || 0) > 0;
            const hasDrCr = (acc.debit || 0) !== 0 || (acc.credit || 0) !== 0;
            // Si quisieras también mostrar cuentas con saldo final ≠ 0 aunque no haya líneas, agrega:
            // const hasEnding = (acc.ending_balance || 0) !== 0;
            return hasLines || hasDrCr; // || hasEnding;
        };

        function pruneGroup(g) {
            // filtrar cuentas por criterio
            g.accounts = g.accounts.filter(acc => includeEmpty || hasPeriodMovement(acc));
            // filtrar hijos recursivamente
            g.children = g.children.filter(ch => pruneGroup(ch));
            // mantener grupo si quedó con cuentas/hijos
            return (g.accounts.length > 0) || (g.children.length > 0);
        }

        if (!includeEmpty) {
            for (let i = roots.length - 1; i >= 0; i--) {
                if (!pruneGroup(roots[i])) roots.splice(i, 1);
            }
        }

        // Totales por grupo (recursivo)
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
        for (const r of roots) computeTotals(r);

        /* ===== ORDEN y items ===== */
        function parseCode(code) {
            return (code ? String(code) : "").split(".").map(s => {
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
                ...g.accounts.map(a => ({kind: "acc", id: a.id, code: a.code, ref: a})),
                ...g.children.map(c => ({kind: "grp", id: c.id, code: c.code_prefix_start, ref: c})),
            ];
            for (const c of g.children) buildItems(c);
        }
        for (const r of roots) buildItems(r);

        // Anotar path / parentPath / level
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
            }
            for (const ch of g.children) annotate(ch, g.path, level + 1);
        }
        for (const r of roots) annotate(r);

        // Estado final
        this.state.groups = roots;
        this.state.parentByPath = parentByPath;
    }
}

class KualeStaticBalanceRenderer extends Component {
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
            await loadJS("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.17.2/xlsx.full.min.js");
            const companies = await this.orm.searchRead("res.company", [["parent_id", "=", false]], ["id", "name"]);
            this.state.companyList = companies;
            if (companies.length > 0) {
                this.state.selectedCompanyId = companies[0].id;
                await this.loadBranches();
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

    /* Filtros */
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
        const companyId = parseInt(ev.target.value);
        this.state.selectedCompanyId = companyId;
        await this.loadBranches();
        await this.props.model.load(
            companyId,
            this.state.selectedBranchId,
            this.state.selectedSatNivel,
            this.state.includeEmpty,
            this.state.fromDate,
            this.state.toDate
        );
        this.state.collapsed = {};
    }

    async onBranchChange(ev) {
        this.state.selectedBranchId = ev.target.value === "null" ? null : parseInt(ev.target.value);
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

    async onSatNivelChange(ev) {
        const satNivel = ev.target.value || null;
        this.state.selectedSatNivel = satNivel;
        await this.props.model.load(
            this.state.selectedCompanyId,
            this.state.selectedBranchId,
            satNivel,
            this.state.includeEmpty,
            this.state.fromDate,
            this.state.toDate
        );
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
        const d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().split("T")[0];
    }

    getToday() {
        return new Date().toISOString().split("T")[0];
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
                title: "Balance Estático",
                company: companyName,
                branch: branchName,
                fromDate: this.state.fromDate,
                toDate: this.state.toDate,
                satNivel: this.state.selectedSatNivel
                    ? (this.state.satNivelList.find(s => s.value === this.state.selectedSatNivel) || {}).label || ""
                    : "Todos",
                includeEmpty: this.state.includeEmpty ? "Sí" : "No",
                rows: this.prepareStaticBalanceRows()
            };

            await generator.generatePDF(reportData);
        } catch (error) {
            console.error("Error al exportar PDF:", error);
            alert("Error al generar el PDF. Por favor, inténtelo nuevamente.");
        }
    }

    prepareStaticBalanceRows() {
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

KualeStaticBalanceRenderer.template = "kuale_static_balance.Renderer";

class KualeStaticBalanceController extends Component {
    setup() {
        this.orm = useService("orm");
        this.model = useState(new this.props.Model(this.orm));
        this.display = {controlPanel: true};
    }
}

KualeStaticBalanceController.template = "kuale_static_balance.View";
KualeStaticBalanceController.components = {Layout};

export const kualeStaticBalanceView = {
    type: "kuale_static_balance",
    display_name: "Kuale Static Balance",
    icon: "fa fa-table",
    multiRecord: true,
    Controller: KualeStaticBalanceController,
    Model: KualeStaticBalanceModel,
    Renderer: KualeStaticBalanceRenderer,
    props() {
        return {Model: KualeStaticBalanceModel, Renderer: KualeStaticBalanceRenderer};
    },
};
registry.category("views").add("kuale_static_balance", kualeStaticBalanceView);

