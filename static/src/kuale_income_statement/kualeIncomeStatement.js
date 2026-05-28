/** @odoo-module **/

import {Layout} from "@web/search/layout";
import {useService} from "@web/core/utils/hooks";
import {Component, onWillStart, useState, onMounted} from "@odoo/owl";
import {KeepLast} from "@web/core/utils/concurrency";
import {registry} from "@web/core/registry";

import {loadJS, loadCSS} from "@web/core/assets";
import {PDFReportGenerator} from "../js/pdf_generator";

class KualeIncomeStatementModel {
    constructor(orm) {
        this.orm = orm;
        this.keeplast = new KeepLast();
        this.state = useState({
            groups: [],
            fromDate: this._startOfMonth(),
            toDate: this._today(),
            mx: null, // nodos y cálculos
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

    /**
     * Carga/recarga datos
     * @param {number|null} company_id
     * @param {number|null} branch_id
     * @param {string} sat_nivel (fijo a "2")
     * @param {boolean} includeEmpty
     * @param {string} fromDate
     * @param {string} toDate
     */
    async load(
        company_id = null,
        branch_id = null,
        sat_nivel = "2",
        includeEmpty = true,
        fromDate = this.state.fromDate,
        toDate = this.state.toDate
    ) {
        this.state.fromDate = fromDate;
        this.state.toDate = toDate;

        const domCompany = company_id ? [["company_id", "=", company_id]] : [];

        // === Grupos (SAT nivel 2) ===
        const groupDomain = [...domCompany, ["sat_nivel", "=", sat_nivel || "2"]];
        const groups = await this.orm.searchRead("account.group", groupDomain, [
            "id",
            "name",
            "group_id",
            "code_prefix_start",
            "sat_nivel",
        ]);

        // === Cuentas (por empresa) ===
        const accounts = await this.orm.searchRead("account.account", domCompany, [
            "id",
            "name",
            "code",
            "group_id",
        ]);

        // === Movimientos: PERIODO y ACUMULADO (YTD) ===
        const yearStart = `${toDate.slice(0, 4)}-01-01`;

        const domainPeriod = [
            ...domCompany,
            ["move_id.state", "=", "posted"],
            ["date", ">=", fromDate],
            ["date", "<=", toDate],
        ];
        const domainYTD = [
            ...domCompany,
            ["move_id.state", "=", "posted"],
            ["date", ">=", yearStart],
            ["date", "<=", toDate],
        ];

        // Agregar filtro de sucursal si está seleccionada
        if (branch_id) {
            domainPeriod.push(["move_id.branch_id", "=", parseInt(branch_id)]);
            domainYTD.push(["move_id.branch_id", "=", parseInt(branch_id)]);
        }

        const periodAgg = await this.orm.readGroup(
            "account.move.line",
            domainPeriod,
            ["debit:sum", "credit:sum", "account_id"],
            ["account_id"]
        );
        const ytdAgg = await this.orm.readGroup(
            "account.move.line",
            domainYTD,
            ["debit:sum", "credit:sum", "account_id"],
            ["account_id"]
        );

        // Mapas por cuenta: periodo/ytd (presentamos P&L como CR - DR)
        const pByAcc = {};
        for (const r of periodAgg) {
            if (r.account_id && r.account_id.length) {
                pByAcc[r.account_id[0]] = (r.credit || 0) - (r.debit || 0);
            }
        }
        const yByAcc = {};
        for (const r of ytdAgg) {
            if (r.account_id && r.account_id.length) {
                yByAcc[r.account_id[0]] = (r.credit || 0) - (r.debit || 0);
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

        // Asignar cuentas a grupo con montos periodo/ytd
        for (const a of accounts) {
            const gid = a.group_id ? a.group_id[0] : null;
            if (!gid || !gById[gid]) continue;
            a.period = pByAcc[a.id] || 0;
            a.ytd   = yByAcc[a.id] || 0;
            gById[gid].accounts.push(a);
        }

        // Vincular jerarquía de grupos
        const roots = [];
        for (const g of groups) {
            const pid = g.group_id ? g.group_id[0] : null;
            if (pid && gById[pid]) gById[pid].children.push(g);
            else roots.push(g);
        }

        // === OnIncludeEmpty (poda por movimiento en periodo) ===
        // Igual que en Aux/TrialBalance: si includeEmpty = false, removemos
        // cuentas sin movimiento del periodo y grupos vacíos.
        const hasPeriodMovement = (a) => (a.period || 0) !== 0;
        const pruneGroup = (g) => {
            // primero niños, para saber si quedan vacíos
            g.children = g.children.map(pruneGroup).filter(Boolean);
            // filtrar cuentas según includeEmpty
            if (!includeEmpty) {
                g.accounts = g.accounts.filter(hasPeriodMovement);
            }
            // mantener si conserva cuentas o hijos
            return (g.accounts.length > 0) || (g.children.length > 0) ? g : null;
        };
        const finalRoots = includeEmpty ? roots : roots.map(pruneGroup).filter(Boolean);

        // Totales por grupo (recursivo) — recalcular después de la poda
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
        for (const r of finalRoots) computeTotals(r);

        // Ordenar por código y construir items *después* de la poda
        const parseCode = (code) => (code ? String(code).split(".").map((s) => +s || 0) : []);
        const cmpCodes = (a, b) => {
            const A = parseCode(a), B = parseCode(b);
            const n = Math.max(A.length, B.length);
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
                ...g.accounts.map((acc) => ({ kind: "acc", id: acc.id, code: acc.code, ref: acc })),
                ...g.children.map((ch) => ({ kind: "grp", id: ch.id, code: ch.code_prefix_start, ref: ch })),
            ];
            for (const ch of g.children) buildItems(ch);
        };
        for (const r of finalRoots) buildItems(r);

        // Utilidades y nodos requeridos (buscar siempre en el árbol final)
        const findByPrefix = (prefix) => {
            const st = [...finalRoots];
            while (st.length) {
                const n = st.pop();
                if ((n.code_prefix_start || "") === prefix) return n;
                if (n.children) st.push(...n.children);
            }
            return null;
        };
        const pOf = (g) => (g ? g.period_total || 0 : 0);
        const yOf = (g) => (g ? g.ytd_total || 0 : 0);

        const g21   = findByPrefix("2.1");
        const g221  = findByPrefix("2.2.1");
        const g222  = findByPrefix("2.2.2");
        const g2221 = findByPrefix("2.2.2.1");
        const g2222 = findByPrefix("2.2.2.2");
        const g2223 = findByPrefix("2.2.2.3");
        const g23   = findByPrefix("2.3");

        const afterNodes = [];
        for (let n = 4; n <= 9; n++) {
            const gx = findByPrefix(`2.${n}`);
            if (gx) afterNodes.push(gx);
        }

        // Líneas calculadas (Periodo y YTD)
        const utilidadBruta_p = pOf(g21) - pOf(g221);
        const utilidadBruta_y = yOf(g21) - yOf(g221);

        const gastosGenerales_p = pOf(g2221) + pOf(g2222) + pOf(g2223);
        const gastosGenerales_y = yOf(g2221) + yOf(g2222) + yOf(g2223);

        const utilidadOp_p = utilidadBruta_p - gastosGenerales_p;
        const utilidadOp_y = utilidadBruta_y - gastosGenerales_y;

        const uoDespuesOtros_p = utilidadOp_p - pOf(g23);
        const uoDespuesOtros_y = utilidadOp_y - yOf(g23);

        // % de líneas calculadas relativo a 2.1
        const baseP = Math.abs(pOf(g21)) || 0;
        const baseY = Math.abs(yOf(g21)) || 0;

        // "utilidad o pérdida de 2.n" (4..9) relativo a utilidad de operación
        const otherCalcs = {};
        for (const gx of afterNodes) {
            otherCalcs[gx.code_prefix_start] = {
                p: utilidadOp_p - pOf(gx),
                y: utilidadOp_y - yOf(gx),
            };
        }

        this.state.groups = finalRoots;
        this.state.mx = {
            g21,
            g221,
            g222,
            g23,
            afterNodes,
            // calculadas
            utilidadBruta_p,
            utilidadBruta_y,
            gastosGenerales_p,
            gastosGenerales_y,
            utilidadOp_p,
            utilidadOp_y,
            uoDespuesOtros_p,
            uoDespuesOtros_y,
            baseP,
            baseY,
            otherCalcs,
        };
    }
}
export class KualeIncomeStatementRenderer extends Component {
    static template = "kuale_income_statement.Renderer";

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
            await loadJS("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.17.2/xlsx.full.min.js")
            const companies = await this.orm.searchRead("res.company", [["parent_id", "=", false]], ["id", "name"]);
            this.state.companyList = companies;
            if (companies.length) {
                this.state.selectedCompanyId = companies[0].id;
                await this.loadBranches(companies[0].id);
                await this.props.model.load(
                    this.state.selectedCompanyId,
                    this.state.selectedBranchId,
                    "2",
                    this.state.includeEmpty,
                    this.state.fromDate,
                    this.state.toDate
                );
            }
        });
    }

    /* ===== Helpers de formato ===== */
    _startOfMonth() { const t=new Date(); return new Date(t.getFullYear(), t.getMonth(), 1).toISOString().slice(0,10); }
    _today()        { const t=new Date(); return t.toISOString().slice(0,10); }
    fmt(n){ return (Number(n||0)).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}); }
    pct(v,b){ b=Math.abs(Number(b||0)); if(!b) return "0.00"; return this.fmt(Number(v||0)*100/b); }

    /* ====== HANDLER DE TOGGLE (lo que falta) ====== */
    onToggle(ev) {
        const tr = ev.currentTarget;
        if (!tr.classList.contains("toggle")) return;

        const id = tr.dataset.id;                 // "g-<id>"
        const tbody = tr.closest("tbody");
        const icon = tr.querySelector(".k-toggle-icon");

        const isOpen = icon && icon.textContent === "[-]";
        if (isOpen) {
            if (icon) icon.textContent = "[+]";
            this._hideDescendants(id, tbody);
        } else {
            if (icon) icon.textContent = "[-]";
            this._showDirectChildren(id, tbody);
        }
    }

    _showDirectChildren(parentDataId, container) {
        // parentDataId = "g-123"  -> hijos tienen clase "parent-g-123"
        const gid = parentDataId.startsWith("g-") ? parentDataId.slice(2) : parentDataId;
        container.querySelectorAll(`tr.parent-g-${CSS.escape(gid)}`).forEach((row) => {
            row.style.display = "table-row";
        });
    }

    _hideDescendants(parentDataId, container) {
        const gid = parentDataId.startsWith("g-") ? parentDataId.slice(2) : parentDataId;
        container.querySelectorAll(`tr.parent-g-${CSS.escape(gid)}`).forEach((row) => {
            row.style.display = "none";
            // Si un hijo era un "toggle", también se colapsa recursivamente
            if (row.classList.contains("toggle")) {
                const ic = row.querySelector(".k-toggle-icon");
                if (ic) ic.textContent = "[+]";
                const cid = row.dataset.id; // "g-<id>" del subgrupo
                if (cid) this._hideDescendants(cid, container);
            }
        });
    }

    /* ===== Métodos auxiliares ===== */
    async loadBranches(companyId) {
        if (!companyId) {
            this.state.branchList = [];
            this.state.selectedBranchId = null;
            return;
        }

        // Cargar sucursales de la compañía seleccionada
        const branches = await this.orm.searchRead("res.company", [["parent_id", "=", companyId]], ["id", "name"]);

        // Si no hay sucursales, incluir la compañía principal
        if (branches.length === 0) {
            const parentCompany = await this.orm.searchRead("res.company", [["id", "=", companyId]], ["id", "name"]);
            this.state.branchList = [{id: "", name: "Todas las sucursales"}, ...parentCompany];
        } else {
            this.state.branchList = [{id: "", name: "Todas las sucursales"}, ...branches];
        }

        this.state.selectedBranchId = this.state.branchList.length > 1 ? this.state.branchList[0].id : null;
    }

    /* ===== Filtros ===== */
    async onCompanyChange(ev) {
        this.state.selectedCompanyId = Number(ev.target.value) || null;
        await this.loadBranches(this.state.selectedCompanyId);
        await this.props.model.load(
            this.state.selectedCompanyId, this.state.selectedBranchId, "2", this.state.includeEmpty, this.state.fromDate, this.state.toDate
        );
    }

    async onBranchChange(ev) {
        const branchId = ev.target.value || null;
        this.state.selectedBranchId = branchId;
        await this.props.model.load(
            this.state.selectedCompanyId, this.state.selectedBranchId, "2", this.state.includeEmpty, this.state.fromDate, this.state.toDate
        );
    }

    async onIncludeEmptyToggle(ev) {
        this.state.includeEmpty = !!ev.target.checked;
        await this.props.model.load(
            this.state.selectedCompanyId, this.state.selectedBranchId, "2", this.state.includeEmpty, this.state.fromDate, this.state.toDate
        );
    }
    async onDateChange() {
        await this.props.model.load(
            this.state.selectedCompanyId, this.state.selectedBranchId, "2", this.state.includeEmpty, this.state.fromDate, this.state.toDate
        );
    }

    // ---- Helper para Excel: devuelve proporción 0..1 para formato %
    ratio(value, base) {
        const b = Math.abs(Number(base || 0));
        if (!b) return 0;
        return Number(value || 0) / b;
    }

    // ---- Exportar a Excel ----
    async exportToExcel() {
        // cargamos XLSX sólo si hace falta

        const wb = XLSX.utils.book_new();

        // === Hoja 1: Filtros / encabezado ===
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

        // === Hoja 2: Estado de resultados ===
        const header = ["Código", "Descripción", "Periodo", "%", "Acumulado", "%"];
        const rows = [header];

        const mx = this.props.model.state.mx || {};
        const fmtName = (name, level) => (level > 0 ? "  ".repeat(level) + name : name);
        const num = (n) => Number((n || 0).toFixed(2));  // redondeo suave

        // Empuja 1 grupo + cuentas + subgrupos, calculando % contra pbase/ybase
        const pushGroup = (g, pbase, ybase, level) => {
            if (!g) return;
            rows.push([
                g.code_prefix_start || "",
                fmtName(g.name || "", level),
                num(g.period_total),
                this.ratio(g.period_total, pbase),
                num(g.ytd_total),
                this.ratio(g.ytd_total, ybase),
            ]);

            // Cuentas directas
            for (const it of (g.items || [])) {
                if (it.kind === "acc") {
                    const a = it.ref;
                    rows.push([
                        a.code || "",
                        fmtName(a.name || "", level + 1),
                        num(a.period),
                        this.ratio(a.period, g.period_total),
                        num(a.ytd),
                        this.ratio(a.ytd, g.ytd_total),
                    ]);
                }
            }
            // Subgrupos
            for (const it of (g.items || [])) {
                if (it.kind === "grp") {
                    pushGroup(it.ref, g.period_total, g.ytd_total, level + 1);
                }
            }
        };

        // 2.1
        if (mx.g21) pushGroup(mx.g21, mx.g21.period_total, mx.g21.ytd_total, 0);

        // 2.2.1
        if (mx.g221) pushGroup(mx.g221, mx.g221.period_total, mx.g221.ytd_total, 0);

        // Utilidad bruta
        rows.push([
            "",
            "Utilidad bruta (2.1 – 2.2.1)",
            num(mx.utilidadBruta_p),
            this.ratio(mx.utilidadBruta_p, mx.baseP),
            num(mx.utilidadBruta_y),
            this.ratio(mx.utilidadBruta_y, mx.baseY),
        ]);
        rows.push(["","","","","",""]); // espacio

        // 2.2.2
        if (mx.g222) pushGroup(mx.g222, mx.g222.period_total, mx.g222.ytd_total, 0);

        // Total de gastos generales
        rows.push([
            "",
            "Total de gastos generales (2.2.2.1 + 2.2.2.2 + 2.2.2.3)",
            num(mx.gastosGenerales_p),
            this.ratio(mx.gastosGenerales_p, mx.baseP),
            num(mx.gastosGenerales_y),
            this.ratio(mx.gastosGenerales_y, mx.baseY),
        ]);

        // Utilidad de operación
        rows.push([
            "",
            "Utilidad de operación (Utilidad bruta – Total de gastos generales)",
            num(mx.utilidadOp_p),
            this.ratio(mx.utilidadOp_p, mx.baseP),
            num(mx.utilidadOp_y),
            this.ratio(mx.utilidadOp_y, mx.baseY),
        ]);
        rows.push(["","","","","",""]); // espacio

        // 2.3
        if (mx.g23) pushGroup(mx.g23, mx.g23.period_total, mx.g23.ytd_total, 0);

        // UO después de otros ingresos y gastos
        rows.push([
            "",
            "Utilidad de operación después de otros ingresos y gastos (− total 2.3)",
            num(mx.uoDespuesOtros_p),
            this.ratio(mx.uoDespuesOtros_p, mx.baseP),
            num(mx.uoDespuesOtros_y),
            this.ratio(mx.uoDespuesOtros_y, mx.baseY),
        ]);
        rows.push(["","","","","",""]); // espacio

        // 2.n (4..9)
        for (const gx of (mx.afterNodes || [])) {
            pushGroup(gx, gx.period_total, gx.ytd_total, 0);
            const calc = mx.otherCalcs[gx.code_prefix_start] || { p: 0, y: 0 };
            rows.push([
                "",
                `Utilidad o pérdida de ${gx.name || gx.code_prefix_start} (${gx.code_prefix_start})`,
                num(calc.p),
                this.ratio(calc.p, mx.baseP),
                num(calc.y),
                this.ratio(calc.y, mx.baseY),
            ]);
            rows.push(["","","","","",""]); // espacio
        }

        const ws = XLSX.utils.aoa_to_sheet(rows);

        // Ancho de columnas
        ws["!cols"] = [
            { wch: 12 },   // Código
            { wch: 60 },   // Descripción
            { wch: 16 },   // Periodo
            { wch: 10 },   // %
            { wch: 16 },   // Acumulado
            { wch: 10 },   // %
        ];

        // Formatos: Periodo/Acumulado => #,##0.00 ; % => 0.00%
        const range = XLSX.utils.decode_range(ws["!ref"]);
        for (let R = 1; R <= range.e.r; R++) {
            // Periodo (col 2) y Acumulado (col 4)
            for (const C of [2, 4]) {
                const cell = ws[XLSX.utils.encode_cell({ r: R, c: C })];
                if (cell && typeof cell.v === "number") { cell.t = "n"; cell.z = "#,##0.00"; }
            }
            // Porcentajes (col 3 y 5) -> escribir proporción 0..1 con formato de %
            for (const C of [3, 5]) {
                const cell = ws[XLSX.utils.encode_cell({ r: R, c: C })];
                if (cell && typeof cell.v === "number") { cell.t = "n"; cell.z = "0.00%"; }
            }
        }

        XLSX.utils.book_append_sheet(wb, ws, "EstadoResultados");

        // nombre de archivo
        const safeCompany = companyName.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 40) || "compania";
        const fname = `estado_resultados_${safeCompany}_${this.state.fromDate}_${this.state.toDate}.xlsx`;
        XLSX.writeFile(wb, fname);
    }

    async exportToPDF() {
        console.log("exportToPDF - Income Statement");
        try {
            const pdfGenerator = new PDFReportGenerator();

            // Preparar datos específicos para Estado de Resultados
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
                title: 'Estado de Resultados',
                company: companyName,
                branch: branchName,
                fromDate: this.state.fromDate,
                toDate: this.state.toDate,
                satNivel: this.state.selectedSatNivel
                    ? (this.state.satNivelList.find(s => s.value === this.state.selectedSatNivel) || {}).label || ""
                    : "Todos",
                includeEmpty: this.state.includeEmpty ? "Sí" : "No",
                rows: this.prepareIncomeStatementRows()
            };

            const safeCompany = companyName.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 40) || "compania";
            const filename = `estado_resultados_${safeCompany}_${this.state.fromDate}_${this.state.toDate}.pdf`;

            await pdfGenerator.generatePDF(reportData, filename);
        } catch (error) {
            console.error('Error generating PDF:', error);
            alert('Error al generar el PDF: ' + error.message);
        }
    }

    prepareIncomeStatementRows() {
        const rows = [];

        // Procesar los grupos del estado de resultados
        if (this.props.model.state.groups) {
            this.processIncomeStatementGroups(this.props.model.state.groups, rows, 0);
        }

        return rows;
    }

    processIncomeStatementGroups(groups, rows, level) {
        groups.forEach(group => {
            // Agregar fila del grupo
            rows.push({
                isGroup: true,
                level: level,
                cells: [
                    { value: group.name || '', isNumber: false },
                    { value: group.period_total || 0, isNumber: true },
                    { value: group.ytd_total || 0, isNumber: true }
                ]
            });

            // Procesar cuentas y subgrupos
            if (group.items) {
                group.items.forEach(item => {
                    if (item.kind === 'acc') {
                        const account = item.ref;
                        rows.push({
                            isGroup: false,
                            level: level + 1,
                            cells: [
                                { value: account.name || '', isNumber: false },
                                { value: account.period_balance || 0, isNumber: true },
                                { value: account.ytd_balance || 0, isNumber: true }
                            ]
                        });
                    } else if (item.kind === 'grp') {
                        this.processIncomeStatementGroups([item.ref], rows, level + 1);
                    }
                });
            }
        });
    }
}

class KualeIncomeStatementController extends Component {
    static template = "kuale_income_statement.View";
    static components = { Layout };
    setup() {
        this.model = useState(new KualeIncomeStatementModel(useService("orm")));
    }
}

export const kualeIncomeStatementView = {
    type: "kuale_income_statement",
    display_name: "Kuale Income Statement",
    icon: "fa fa-table",
    multiRecord: true,
    Controller: KualeIncomeStatementController,
    Model: KualeIncomeStatementModel,
    Renderer: KualeIncomeStatementRenderer,
    props() {
        return { Model: KualeIncomeStatementModel, Renderer: KualeIncomeStatementRenderer };
    },
};
registry.category("views").add("kuale_income_statement", kualeIncomeStatementView);


