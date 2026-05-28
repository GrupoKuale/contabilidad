/** @odoo-module **/

import {Layout} from "@web/search/layout";
import {useService} from "@web/core/utils/hooks";
import {Component, onWillStart, useState, onMounted} from "@odoo/owl";
import {KeepLast} from "@web/core/utils/concurrency";
import {registry} from "@web/core/registry";

import {loadJS, loadCSS} from "@web/core/assets";
import {PDFReportGenerator} from "../js/pdf_generator";

class KualeFinancialPositionModel {
    constructor(orm) {
        this.orm = orm;
        this.keeplast = new KeepLast();
        this.state = useState({
            groups: [],
            fromDate: this._startOfMonth(),
            toDate: this._today(),
            mx: null, // referencias y totales (1.1.1, 1.1.2, 1.2.1, 1.2.2, 1.3, etc.)
        });
    }

    _startOfMonth() {
        const t = new Date();
        return new Date(t.getFullYear(), t.getMonth(), 1).toISOString().slice(0, 10);
    }

    _today() {
        const t = new Date();
        return t.toISOString().slice(0, 10);
    }

    async load(
        company_id = null,
        branch_id = null,
        sat_nivel = "",
        includeEmpty = true,
        fromDate = this.state.fromDate,
        toDate = this.state.toDate
    ) {
        this.state.fromDate = fromDate;
        this.state.toDate = toDate;

        const domCompany = company_id ? [["company_id", "=", company_id]] : [];
        const domBranch = branch_id ? [["branch_id", "=", parseInt(branch_id)]] : [];

        /* === Grupos (SAT nivel 1) === */
        const groupDomain = [...domCompany];
        const groups = await this.orm.searchRead("account.group", groupDomain, [
            "id", "name", "group_id", "code_prefix_start", "sat_nivel"
        ]);

        /* === Cuentas por empresa === */
        const accounts = await this.orm.searchRead("account.account", domCompany, [
            "id", "name", "code", "group_id"
        ]);

        /* === Movimientos: PERIOD (rango) y YTD (año a la fecha) ===
         * Para BS usamos neto (Débito − Crédito) con signo contable estándar.
         */
        const yearStart = `${toDate.slice(0, 4)}-01-01`;

        const domainPeriod = [
            ...domCompany,
            ...domBranch,
            ["move_id.state", "=", "posted"],
            ["date", ">=", fromDate],
            ["date", "<=", toDate],
        ];
        const domainYTD = [
            ...domCompany,
            ...domBranch,
            ["move_id.state", "=", "posted"],
            ["date", ">=", yearStart],
            ["date", "<=", toDate],
        ];

        const periodAgg = await this.orm.readGroup(
            "account.move.line", domainPeriod,
            ["debit:sum", "credit:sum", "account_id"], ["account_id"]
        );
        const ytdAgg = await this.orm.readGroup(
            "account.move.line", domainYTD,
            ["debit:sum", "credit:sum", "account_id"], ["account_id"]
        );

        // Mapas por cuenta: periodo / ytd  (DEBITO − CREDITO)
        const pByAcc = {};
        for (const r of periodAgg) {
            if (r.account_id && r.account_id.length) {
                pByAcc[r.account_id[0]] = (r.debit || 0) - (r.credit || 0);
            }
        }
        const yByAcc = {};
        for (const r of ytdAgg) {
            if (r.account_id && r.account_id.length) {
                yByAcc[r.account_id[0]] = (r.debit || 0) - (r.credit || 0);
            }
        }

        // === Construcción del árbol ===
        const gById = {};
        for (const g of groups) {
            g.children = [];
            g.accounts = [];
            g.period_total = 0;
            g.ytd_total = 0;
            gById[g.id] = g;
        }

        // Asignar cuentas con montos (y flags de movimiento de periodo)
        for (const a of accounts) {
            const gid = a.group_id ? a.group_id[0] : null;
            if (!gid || !gById[gid]) continue;
            a.period = pByAcc[a.id] || 0;
            a.ytd = yByAcc[a.id] || 0;
            // para onIncludeEmpty (misma idea que en Aux/TrialBalance):
            a._hasPeriodMovement = (a.period || 0) !== 0;
            gById[gid].accounts.push(a);
        }

        // Vincular jerarquía
        let roots = [];
        for (const g of groups) {
            const pid = g.group_id ? g.group_id[0] : null;
            if (pid && gById[pid]) gById[pid].children.push(g);
            else roots.push(g);
        }

        // === onIncludeEmpty: podar cuentas/grupos sin movimiento en el periodo ===
        const hasPeriodMovement = (acc) => !!acc._hasPeriodMovement;

        function pruneGroup(g) {
            // filtra cuentas
            g.accounts = g.accounts.filter(acc => includeEmpty || hasPeriodMovement(acc));
            // filtra hijos recursivamente
            g.children = g.children.filter(ch => pruneGroup(ch));
            // mantener grupo solo si tiene algo
            return (g.accounts.length > 0) || (g.children.length > 0);
        }

        if (!includeEmpty) {
            const newRoots = [];
            for (const r of roots) {
                if (pruneGroup(r)) newRoots.push(r);
            }
            roots = newRoots;
        }

        // Totales (recursivo)
        const computeTotals = (g) => {
            let p = 0, y = 0;
            for (const a of g.accounts) {
                p += a.period;
                y += a.ytd;
            }
            for (const c of g.children) {
                computeTotals(c);
                p += c.period_total;
                y += c.ytd_total;
            }
            g.period_total = p;
            g.ytd_total = y;
        };
        for (const r of roots) computeTotals(r);

        // Orden por código
        const parseCode = (code) => (code ? String(code).split(".").map(s => +s || 0) : []);
        const cmpCodes = (a, b) => {
            const A = parseCode(a), B = parseCode(b), n = Math.max(A.length, B.length);
            for (let i = 0; i < n; i++) {
                const x = A[i] || 0, y = B[i] || 0;
                if (x !== y) return x - y;
            }
            return String(a || "").localeCompare(String(b || ""));
        };
        const buildItems = (g) => {
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
        };
        for (const r of roots) buildItems(r);

        // --- utilidades para localizar prefijos y sumar ---
        const findByPrefix = (prefix) => {
            const st = [...roots];
            while (st.length) {
                const n = st.pop();
                if ((n.code_prefix_start || "") === prefix) return n;
                if (n.children) st.push(...n.children);
            }
            return null;
        };
        const pOf = (g) => (g ? g.period_total || 0 : 0);
        const yOf = (g) => (g ? g.ytd_total || 0 : 0);

        const totalsOf = (g) => g ? {p: g.period_total || 0, y: g.ytd_total || 0} : {p: 0, y: 0};
        const addT = (a, b) => ({p: (a.p || 0) + (b.p || 0), y: (a.y || 0) + (b.y || 0)});
        const subtract = (a, b) => ({p: (a.p || 0) - (b.p || 0), y: (a.y || 0) - (b.y || 0)});

        // Activo
        const g111 = findByPrefix("1.1.1");
        const g112 = findByPrefix("1.1.2");
        const t111 = totalsOf(g111);
        const t112 = totalsOf(g112);
        const t11 = addT(t111, t112);

        // Pasivo
        const g121 = findByPrefix("1.2.1");
        const g122 = findByPrefix("1.2.2");
        const t121 = totalsOf(g121);
        const t122 = totalsOf(g122);
        const t12 = addT(t121, t122);

        // Capital
        const g13 = findByPrefix("1.3");
        const t13 = totalsOf(g13);

        // Estado de resultados para utilidades
        const g21 = findByPrefix("2.1");
        const g221 = findByPrefix("2.2.1");
        const g2221 = findByPrefix("2.2.2.1");
        const g2222 = findByPrefix("2.2.2.2");
        const g2223 = findByPrefix("2.2.2.3");

        const utilidadBruta_p = pOf(g21) - pOf(g221);
        const utilidadBruta_y = yOf(g21) - yOf(g221);
        const gastosGenerales_p = pOf(g2221) + pOf(g2222) + pOf(g2223);
        const gastosGenerales_y = yOf(g2221) + yOf(g2222) + yOf(g2223);

        const utilidadOp_p = utilidadBruta_p - gastosGenerales_p;
        const utilidadOp_y = utilidadBruta_y - gastosGenerales_y;
        const tOp = {p: utilidadOp_p, y: utilidadOp_y};

        // 2.7
        const g27 = findByPrefix("2.7");
        const t27 = totalsOf(g27);

        // pérdidas de la operación y total final pasivo+capital
        const tOpLoss = subtract(tOp, t27);
        let tLiabEq = addT(t12, t13);
        tLiabEq = addT(tLiabEq, tOpLoss);

        this.state.groups = roots;
        this.state.mx = {g111, g112, g121, g122, g13, t111, t112, t11, t121, t122, t12, t13, tLiabEq, g27, t27, tOpLoss};
    }
}

class KualeFinancialPositionRenderer extends Component {
    static template = "kuale_financial_position.Renderer";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            companyList: [],
            selectedCompanyId: null,
            branchList: [],
            selectedBranchId: null,
            includeEmpty: true,
            fromDate: this._startOfMonth(),
            toDate: this._today(),
        });

        onWillStart(async () => {
            await loadJS("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.17.2/xlsx.full.min.js");
            const companies = await this.orm.searchRead("res.company", [["parent_id", "=", false]], ["id", "name"]);
            this.state.companyList = companies;
            if (companies.length) {
                this.state.selectedCompanyId = companies[0].id;
                await this.loadBranches();
                await this.props.model.load(
                    this.state.selectedCompanyId, this.state.selectedBranchId, "1", this.state.includeEmpty, this.state.fromDate, this.state.toDate
                );
            }
        });
    }

    // Toggle
    onToggle(ev) {
        const tr = ev.currentTarget;
        if (!tr.classList.contains("toggle")) return;
        const tbody = tr.closest("tbody");
        const icon = tr.querySelector(".k-toggle-icon");
        const id = tr.getAttribute("data-id");
        const isOpen = icon && icon.textContent === "[-]";
        if (isOpen) {
            if (icon) icon.textContent = "[+]";
            this._hideDesc(id, tbody);
        } else {
            if (icon) icon.textContent = "[-]";
            this._showChildren(id, tbody);
        }
    }

    _showChildren(parentId, root) {
        root.querySelectorAll(`tr.child-row.parent-${CSS.escape(parentId)}`).forEach(r => {
            r.style.display = "table-row";
        });
    }

    _hideDesc(parentId, root) {
        root.querySelectorAll(`tr.child-row.parent-${CSS.escape(parentId)}`).forEach(r => {
            r.style.display = "none";
            if (r.classList.contains("toggle")) {
                const ic = r.querySelector(".k-toggle-icon");
                if (ic) ic.textContent = "[+]";
                const cid = r.getAttribute("data-id");
                if (cid) this._hideDesc(cid, root);
            }
        });
    }

    // Filtros
    _startOfMonth() {
        const t = new Date();
        return new Date(t.getFullYear(), t.getMonth(), 1).toISOString().slice(0, 10);
    }

    _today() {
        const t = new Date();
        return t.toISOString().slice(0, 10);
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
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, "1", this.state.includeEmpty, this.state.fromDate, this.state.toDate);
    }

    async onBranchChange(ev) {
        this.state.selectedBranchId = ev.target.value === "null" ? null : parseInt(ev.target.value);
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, "1", this.state.includeEmpty, this.state.fromDate, this.state.toDate);
    }

    async onIncludeEmptyToggle(ev) {
        this.state.includeEmpty = !!ev.target.checked;
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, "1", this.state.includeEmpty, this.state.fromDate, this.state.toDate);
    }

    async onDateChange() {
        await this.props.model.load(this.state.selectedCompanyId, this.state.selectedBranchId, "1", this.state.includeEmpty, this.state.fromDate, this.state.toDate);
    }

    // helpers de formato
    fmt(n) {
        return (Number(n || 0)).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    pct(v, b) {
        b = Math.abs(Number(b || 0));
        if (!b) return "0.00";
        return this.fmt(Number(v || 0) * 100 / b);
    }

    ratio(value, base) {
        const b = Math.abs(Number(base || 0));
        if (!b) return 0;
        return Number(value || 0) / b;
    }

    async exportToExcel() {
        const mx = this.props.model.state.mx;
        if (!mx) return;

        // ==== Libro y hoja de filtros ====
        const wb = XLSX.utils.book_new();

        const companyName = (this.state.companyList.find(c => c.id === this.state.selectedCompanyId) || {}).name || "";
        const filters = [
            ["Compañía", companyName],
            ["Desde", this.state.fromDate],
            ["Hasta", this.state.toDate],
            ["Incluir vacíos", this.state.includeEmpty ? "Sí" : "No"],
            ["Generado", new Date().toISOString()],
        ];
        const wsFilters = XLSX.utils.aoa_to_sheet(filters);
        XLSX.utils.book_append_sheet(wb, wsFilters, "Filtros");

        // ==== Hoja del reporte ====
        const header = ["Código", "Descripción", "Periodo", "%", "Acumulado", "%"];
        const rows = [header];

        const num = (n) => Number((n || 0).toFixed(2));
        const indent = (lvl) => "  ".repeat(Math.max(0, lvl));

        // Empuja un grupo con cuentas y subgrupos; % contra pbase / ybase
        const pushGroup = (g, pbase, ybase, level) => {
            if (!g) return;
            rows.push([
                g.code_prefix_start || "",
                `${indent(level)}${g.name || ""}`,
                num(g.period_total),
                this.ratio(g.period_total, pbase),
                num(g.ytd_total),
                this.ratio(g.ytd_total, ybase),
            ]);

            // cuentas directas
            for (const it of g.items || []) {
                if (it.kind === "acc") {
                    const a = it.ref;
                    rows.push([
                        a.code || "",
                        `${indent(level + 1)}${a.name || ""}`,
                        num(a.period),
                        this.ratio(a.period, g.period_total),
                        num(a.ytd),
                        this.ratio(a.ytd, g.ytd_total),
                    ]);
                }
            }
            // subgrupos
            for (const it of g.items || []) {
                if (it.kind === "grp") pushGroup(it.ref, g.period_total, g.ytd_total, level + 1);
            }
        };

        // Fila de total calculado
        const pushTotal = (label, p, pbase, y, ybase) => {
            rows.push(["", label, num(p), this.ratio(p, pbase), num(y), this.ratio(y, ybase)]);
        };

        // === Secuencia idéntica a la vista ===
        if (mx.g111) {
            pushGroup(mx.g111, mx.t11.p, mx.t11.y, 0);
            pushTotal("Total de activos a corto plazo (1.1.1)", mx.t111.p, mx.t11.p, mx.t111.y, mx.t11.y);
            rows.push(["", "", "", "", "", ""]);
        }
        if (mx.g112) {
            pushGroup(mx.g112, mx.t11.p, mx.t11.y, 0);
            pushTotal("Total de activos a largo plazo (1.1.2)", mx.t112.p, mx.t11.p, mx.t112.y, mx.t11.y);
            rows.push(["", "", "", "", "", ""]);
        }
        pushTotal("Total de activo (1.1 = 1.1.1 + 1.1.2)", mx.t11.p, mx.t11.p, mx.t11.y, mx.t11.y);
        rows.push(["", "", "", "", "", ""]);

        if (mx.g121) {
            pushGroup(mx.g121, mx.t12.p, mx.t12.y, 0);
            pushTotal("Total de pasivos a corto plazo (1.2.1)", mx.t121.p, mx.t12.p, mx.t121.y, mx.t12.y);
            rows.push(["", "", "", "", "", ""]);
        }
        if (mx.g122) {
            pushGroup(mx.g122, mx.t12.p, mx.t12.y, 0);
            pushTotal("Total de pasivos a largo plazo (1.2.2)", mx.t122.p, mx.t12.p, mx.t122.y, mx.t12.y);
            rows.push(["", "", "", "", "", ""]);
        }
        pushTotal("Total de pasivo (1.2 = 1.2.1 + 1.2.2)", mx.t12.p, mx.t12.p, mx.t12.y, mx.t12.y);
        rows.push(["", "", "", "", "", ""]);

        if (mx.g13) {
            // en pantalla usas % contra sí mismo; lo conservamos
            pushGroup(mx.g13, mx.t13.p, mx.t13.y, 0);
            pushTotal("Total de capital contable (1.3)", mx.t13.p, mx.t13.p, mx.t13.y, mx.t13.y);
            rows.push(["", "", "", "", "", ""]);
        }

        pushTotal("Total del pasivo y capital contable (1.2 + 1.3)", mx.tLiabEq.p, mx.tLiabEq.p, mx.tLiabEq.y, mx.tLiabEq.y);

        // AOA -> Sheet
        const ws = XLSX.utils.aoa_to_sheet(rows);

        // Ancho de columnas
        ws["!cols"] = [
            {wch: 12},  // Código
            {wch: 60},  // Descripción
            {wch: 16},  // Periodo
            {wch: 10},  // %
            {wch: 16},  // Acumulado
            {wch: 10},  // %
        ];

        // Formatos: monto = #,##0.00 ; % = 0.00% (valores ya están en 0..1)
        const range = XLSX.utils.decode_range(ws["!ref"]);
        for (let R = 1; R <= range.e.r; R++) {
            for (const C of [2, 4]) { // Periodo y Acumulado
                const cell = ws[XLSX.utils.encode_cell({r: R, c: C})];
                if (cell && typeof cell.v === "number") {
                    cell.t = "n";
                    cell.z = "#,##0.00";
                }
            }
            for (const C of [3, 5]) { // %
                const cell = ws[XLSX.utils.encode_cell({r: R, c: C})];
                if (cell && typeof cell.v === "number") {
                    cell.t = "n";
                    cell.z = "0.00%";
                }
            }
        }

        XLSX.utils.book_append_sheet(wb, ws, "Estado Sit. Fin.");

        // Nombre de archivo
        const safeCompany = companyName.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 40) || "compania";
        const fname = `estado_situacion_financiera_${safeCompany}_${this.state.fromDate}_${this.state.toDate}.xlsx`;
        XLSX.writeFile(wb, fname);
    }

    async exportToPDF() {
        console.log("exportToPDF - Financial Position");
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
                title: 'Estado de Situación Financiera',
                company: companyName,
                branch: branchName,
                fromDate: this.state.fromDate,
                toDate: this.state.toDate,
                satNivel: this.state.selectedSatNivel
                    ? (this.state.satNivelList.find(s => s.value === this.state.selectedSatNivel) || {}).label || ""
                    : "Todos",
                includeEmpty: this.state.includeEmpty ? "Sí" : "No",
                rows: this.prepareFinancialPositionRows()
            };

            const safeCompany = companyName.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 40) || "compania";
            const filename = `estado_situacion_financiera_${safeCompany}_${this.state.toDate}.pdf`;

            await pdfGenerator.generatePDF(reportData, filename);
        } catch (error) {
            console.error('Error generating PDF:', error);
            alert('Error al generar el PDF: ' + error.message);
        }
    }

    prepareFinancialPositionRows() {
        const rows = [];

        if (this.props.model.state.groups) {
            this.processFinancialPositionGroups(this.props.model.state.groups, rows, 0);
        }

        return rows;
    }

    processFinancialPositionGroups(groups, rows, level) {
        groups.forEach(group => {
            rows.push({
                isGroup: true,
                level: level,
                cells: [
                    { value: group.name || '', isNumber: false },
                    { value: group.ending_balance_total || 0, isNumber: true }
                ]
            });

            if (group.items) {
                group.items.forEach(item => {
                    if (item.kind === 'acc') {
                        const account = item.ref;
                        rows.push({
                            isGroup: false,
                            level: level + 1,
                            cells: [
                                { value: account.name || '', isNumber: false },
                                { value: account.ending_balance || 0, isNumber: true }
                            ]
                        });
                    } else if (item.kind === 'grp') {
                        this.processFinancialPositionGroups([item.ref], rows, level + 1);
                    }
                });
            }
        });
    }
}

class KualeFinancialPositionController extends Component {
    static template = "kuale_financial_position.View";
    static components = {Layout};

    setup() {
        this.orm = useService("orm");
        this.model = useState(new this.props.Model(this.orm));
        this.display = {controlPanel: true};
    }
}

export const kualeFinancialPositionView = {
    type: "kuale_financial_position",
    display_name: "Kuale Finacial Position",
    icon: "fa fa-table",
    multiRecord: true,
    Controller: KualeFinancialPositionController,
    Model: KualeFinancialPositionModel,
    Renderer: KualeFinancialPositionRenderer,
    props() {
        return {Model: KualeFinancialPositionModel, Renderer: KualeFinancialPositionRenderer};
    },
};
registry.category("views").add("kuale_financial_position", kualeFinancialPositionView);

