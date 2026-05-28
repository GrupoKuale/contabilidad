/** @odoo-module **/

/**
 * Utilidades para generar reportes PDF usando HTML y CSS
 * Compatible con todos los reportes financieros de Kuale
 */

export class PDFReportGenerator {
    constructor() {
        this.templatePath = '/contabilidad_kuale/static/src/templates/report_pdf_template.html';
    }

    /**
     * Formatea un número para mostrar en el reporte
     */
    formatNumber(value) {
        if (value === null || value === undefined || value === '') return '0.00';
        const num = typeof value === 'string' ? parseFloat(value) : value;
        return isNaN(num) ? '0.00' : num.toLocaleString('es-MX', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    /**
     * Obtiene la plantilla HTML base
     */
    async getTemplate() {
        try {
            console.log('=== FORZANDO TEMPLATE DE FALLBACK ===');
            console.log('Usando template interno con placeholders correctos');
            return this.getFallbackTemplate();
        } catch (error) {
            console.error('Error loading PDF template:', error);
            console.warn('Usando template de fallback debido al error');
            // Template básico de fallback
            return this.getFallbackTemplate();
        }
    }

    /**
     * Template básico de fallback si no se puede cargar el archivo
     */
    getFallbackTemplate() {
        return `
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{{reportTitle}}</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                
                body { 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    margin: 15px; 
                    background: #fafafa;
                    color: #2c3e50;
                    font-size: 11px;
                    line-height: 1.4;
                }
                
                .report-container {
                    background: white;
                    padding: 25px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    border-radius: 8px;
                    max-width: 100%;
                }
                
                .header { 
                    text-align: center; 
                    margin-bottom: 25px; 
                    border-bottom: 3px solid #3498db; 
                    padding-bottom: 15px;
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    padding: 20px;
                    border-radius: 8px 8px 0 0;
                    margin: -25px -25px 25px -25px;
                }
                
                .company-name { 
                    font-size: 20px; 
                    font-weight: bold; 
                    color: #2c3e50;
                    margin-bottom: 8px;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }
                
                .report-title { 
                    font-size: 16px; 
                    margin: 8px 0; 
                    color: #34495e;
                    font-weight: 600;
                }
                
                .report-period {
                    font-size: 13px;
                    color: #7f8c8d;
                    font-style: italic;
                }
                
                .filters-simple {
                    background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf1 100%);
                    border-left: 5px solid #3498db;
                    padding: 12px 15px;
                    margin: 20px 0;
                    border-radius: 6px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                
                .filters-simple strong {
                    color: #2c3e50;
                    font-weight: 700;
                    font-size: 12px;
                    display: block;
                    margin-bottom: 5px;
                }
                
                .filters-list {
                    color: #34495e;
                    font-size: 11px;
                    line-height: 1.5;
                }
                
                table { 
                    width: 100%; 
                    border-collapse: collapse; 
                    margin-top: 15px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    border-radius: 8px;
                    overflow: hidden;
                }
                
                th { 
                    background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
                    color: white;
                    font-weight: 700;
                    padding: 12px 8px;
                    text-align: center;
                    font-size: 10px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    border-right: 1px solid rgba(255,255,255,0.2);
                }
                
                th:last-child { border-right: none; }
                
                td { 
                    border: 1px solid #e0e0e0; 
                    padding: 8px 6px; 
                    font-size: 10px;
                    background: white;
                }
                
                tr:nth-child(even) td { background: #f8f9fa; }
                tr:hover td { background: #e3f2fd; }
                
                .number { 
                    text-align: right; 
                    font-weight: 600;
                    font-family: 'Courier New', monospace;
                    color: #2c3e50;
                }
                
                .group-row { 
                    background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%) !important;
                    font-weight: bold;
                    color: white;
                }
                
                .group-row td {
                    background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%) !important;
                    font-weight: 700;
                    font-size: 11px;
                    color: white;
                }
                
                .category-principal {
                    background: linear-gradient(135deg, #2980b9 0%, #21618c 100%) !important;
                    color: white;
                    font-weight: bold;
                }
                
                .category-principal td {
                    background: linear-gradient(135deg, #2980b9 0%, #21618c 100%) !important;
                    color: white;
                    font-weight: 700;
                    font-size: 11px;
                }
                
                .total-row {
                    background: linear-gradient(135deg, #27ae60 0%, #229954 100%) !important;
                    color: white;
                    font-weight: bold;
                }
                
                .total-row td {
                    background: linear-gradient(135deg, #27ae60 0%, #229954 100%) !important;
                    color: white;
                    font-weight: 700;
                    font-size: 11px;
                }
                
                .subtotal-row {
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%) !important;
                    color: white;
                    font-weight: bold;
                }
                
                .subtotal-row td {
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%) !important;
                    color: white;
                    font-weight: 700;
                }
                
                .indent-1 { padding-left: 25px; border-left: 3px solid #3498db; }
                .indent-2 { padding-left: 45px; border-left: 3px solid #9b59b6; }
                .indent-3 { padding-left: 65px; border-left: 3px solid #e67e22; }
                
                .footer {
                    margin-top: 25px;
                    text-align: center;
                    padding-top: 15px;
                    border-top: 2px solid #ecf0f1;
                    font-size: 11px;
                    color: #7f8c8d;
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 6px;
                }
                
                .account-code {
                    font-weight: 700;
                    color: #3498db;
                    font-family: 'Courier New', monospace;
                }
                
                .account-name {
                    font-weight: 600;
                    color: #2c3e50;
                }
                
                .positive-balance {
                    color: #27ae60;
                    font-weight: 700;
                }
                
                .negative-balance {
                    color: #e74c3c;
                    font-weight: 700;
                }
                
                .zero-balance {
                    color: #95a5a6;
                }
                
                @media print {
                    body { margin: 0; background: white; }
                    .report-container { box-shadow: none; }
                    tr:hover td { background: inherit !important; }
                }
            </style>
        </head>
        <body>
            <div class="report-container">
                <div class="header">
                    <div class="company-name">{{companyName}}</div>
                    <div class="report-title">{{reportTitle}}</div>
                    <div class="report-period">{{reportPeriod}}</div>
                </div>
                
                <div class="filters-simple">
                    <strong>Filtros Aplicados</strong>
                    <div class="filters-list">FILTROS_PLACEHOLDER</div>
                </div>
                
                <table>
                    <thead>
                        <tr>COLUMNS_PLACEHOLDER</tr>
                    </thead>
                    <tbody>ROWS_PLACEHOLDER</tbody>
                </table>
                
                <div class="footer">
                    <strong>Generado el {{generatedDate}}</strong><br>
                    <em>Sistema Contable Kuale - Balance de Comprobación</em>
                </div>
            </div>
        </body>
        </html>`;
    }

    /**
     * Renderiza la plantilla con los datos proporcionados
     */
    renderTemplate(template, data) {
        let html = template;

        // Reemplazar variables simples
        const simpleVars = ['companyName', 'reportTitle', 'reportPeriod', 'generatedDate'];
        simpleVars.forEach(varName => {
            const regex = new RegExp(`{{${varName}}}`, 'g');
            html = html.replace(regex, data[varName] || '');
        });

        // Procesar filtros de manera simple
        let filtersText = '';
        if (data.filters && data.filters.length > 0) {
            const filterTexts = data.filters.map(filter => `${filter.label}: ${filter.value}`);
            filtersText = filterTexts.join(' | ');
        }
        console.log('=== PROCESANDO FILTROS ===');
        console.log('Filtros data:', data.filters);
        console.log('Texto generado:', filtersText);

        // Reemplazar placeholder simple
        const originalHtml = html;
        html = html.replace('FILTROS_PLACEHOLDER', filtersText);
        console.log('Reemplazo de filtros realizado:', originalHtml.includes('FILTROS_PLACEHOLDER'), '->', !html.includes('FILTROS_PLACEHOLDER'));

        // Procesar columnas de manera simple
        let columnsHtml = '';
        if (data.columns && data.columns.length > 0) {
            data.columns.forEach(column => {
                const numberClass = column.isNumber ? 'number' : '';
                columnsHtml += `<th class="${numberClass}">${column.title}</th>`;
            });
        }
        console.log('=== PROCESANDO COLUMNAS ===');
        console.log('Columnas data:', data.columns);
        console.log('HTML generado:', columnsHtml);

        // Reemplazar placeholder simple
        html = html.replace('COLUMNS_PLACEHOLDER', columnsHtml);
        console.log('Reemplazo de columnas realizado:', !html.includes('COLUMNS_PLACEHOLDER'));

        // Procesar filas de manera simple
        let rowsHtml = '';
        if (data.rows && data.rows.length > 0) {
            data.rows.forEach(row => {
                let rowClasses = '';

                // Convertir datos del nuevo formato al formato de celdas si es necesario
                if (!row.cells && (row.code !== undefined || row.name !== undefined)) {
                    console.log('Procesando fila:', row.code, row.name);
                    console.log('Datos originales:', {
                        initialBalance: row.initialBalance,
                        debit: row.debit,
                        credit: row.credit,
                        endingBalance: row.endingBalance
                    });

                    // Calcular SIEMPRE el saldo final usando la fórmula contable
                    const initialBalance = parseFloat(row.initialBalance || 0);
                    const debit = parseFloat(row.debit || 0);
                    const credit = parseFloat(row.credit || 0);
                    const calculatedEndingBalance = initialBalance + debit - credit;

                    console.log('Saldo final calculado:', calculatedEndingBalance);

                    // Convertir formato nuevo a formato de celdas
                    row.cells = [
                        { value: row.code || '', isNumber: false },
                        { value: row.name || '', isNumber: false },
                        { value: initialBalance, isNumber: true },
                        { value: debit, isNumber: true },
                        { value: credit, isNumber: true },
                        { value: calculatedEndingBalance, isNumber: true }
                    ];

                    // Determinar si es un grupo basado en el tipo
                    if (row.type === 'group') {
                        row.isGroup = true;
                    }
                }

                if (row.isGroup) rowClasses += `group-row level-${row.level || 0}`;
                if (row.isTotal) rowClasses += ' total-row';
                if (row.isSubtotal) rowClasses += ' subtotal-row';

                // Detectar SOLO las filas principales exactas por el código y nombre
                if (row.cells && row.cells.length > 1) {
                    const firstCell = String(row.cells[0].value || '').trim(); // Código
                    const secondCell = String(row.cells[1].value || '').toUpperCase().trim(); // Nombre

                    // Solo resaltar las filas principales de categorías (códigos de 4 dígitos)
                    if ((firstCell === '5100' && secondCell.includes('ACTIVO CIRCULANTE')) ||
                        (firstCell === '6100' && secondCell.includes('PASIVO CORTO PLAZO')) ||
                        (firstCell === '7000' && secondCell === 'CAPITAL') ||
                        (firstCell === '8000' && secondCell === 'INGRESOS') ||
                        (firstCell === '9000' && secondCell === 'GASTOS')) {
                        rowClasses += ' category-principal';
                    }
                }

                rowsHtml += `<tr class="${rowClasses}">`;

                if (row.cells && row.cells.length > 0) {
                    // Recalcular saldo final si ya viene en formato de celdas
                    if (row.cells.length >= 6) {
                        const saldoInicial = parseFloat(row.cells[2]?.value || 0);
                        const debito = parseFloat(row.cells[3]?.value || 0);
                        const credito = parseFloat(row.cells[4]?.value || 0);
                        const saldoFinalCalculado = saldoInicial + debito - credito;

                        console.log(`Recalculando ${row.cells[0]?.value || 'N/A'}: ${saldoInicial} + ${debito} - ${credito} = ${saldoFinalCalculado}`);

                        // Actualizar la celda del saldo final
                        row.cells[5] = {
                            value: saldoFinalCalculado,
                            isNumber: true
                        };
                    }

                    row.cells.forEach(cell => {
                        let cellClasses = '';
                        if (cell.isNumber) cellClasses += 'number ';
                        if (row.isGroup) cellClasses += `indent-${row.level || 0}`;

                        const cellValue = cell.isNumber ? this.formatNumber(cell.value) : (cell.value || '');
                        rowsHtml += `<td class="${cellClasses}">${cellValue}</td>`;
                    });
                }

                rowsHtml += '</tr>';
            });
        }
        console.log('=== PROCESANDO FILAS ===');
        console.log('Filas data:', data.rows?.length || 0);
        console.log('Primeras 2 filas:', data.rows?.slice(0, 2));
        console.log('HTML generado (primeros 200 caracteres):', rowsHtml.substring(0, 200));

        // Reemplazar placeholder simple
        html = html.replace('ROWS_PLACEHOLDER', rowsHtml);
        console.log('Reemplazo de filas realizado:', !html.includes('ROWS_PLACEHOLDER'));

        console.log('Template procesado completamente');

        return html;
    }

    /**
     * Genera y descarga un PDF usando los datos del reporte
     */
    async generatePDF(reportData, filename = 'reporte.pdf') {
        try {
            console.log('Generating PDF with data:', reportData);

            // Preparar datos completos con columnas y filtros
            const completeData = this.prepareReportData(reportData);

            // Obtener la plantilla
            const template = await this.getTemplate();

            // Renderizar HTML con los datos
            const html = this.renderTemplate(template, completeData);

            // DEBUG: Mostrar HTML final
            console.log('=== HTML FINAL ANTES DE IMPRIMIR ===');
            console.log('HTML contiene placeholders?', {
                filtros: html.includes('FILTROS_PLACEHOLDER'),
                columns: html.includes('COLUMNS_PLACEHOLDER'),
                rows: html.includes('ROWS_PLACEHOLDER'),
                handlebars: html.includes('{{#each'),
                filtrosAplicados: html.includes('Filtros Aplicados')
            });
            console.log('HTML (primeros 1000 caracteres):', html.substring(0, 1000));

            // Buscar específicamente la sección de filtros
            const filtrosStart = html.indexOf('Filtros Aplicados');
            if (filtrosStart > -1) {
                console.log('Sección de filtros encontrada:', html.substring(filtrosStart, filtrosStart + 300));
            } else {
                console.log('❌ NO se encontró la sección de Filtros Aplicados');
            }

            // Crear una ventana temporal para generar el PDF
            const printWindow = window.open('', '_blank');
            if (!printWindow) {
                throw new Error('No se pudo abrir la ventana de impresión. Verifique que no esté bloqueada por el navegador.');
            }

            printWindow.document.write(html);
            printWindow.document.close();

            // Esperar a que se cargue el contenido
            printWindow.onload = () => {
                printWindow.focus();
                setTimeout(() => {
                    printWindow.print();
                    printWindow.close();
                }, 1000);
            };

        } catch (error) {
            console.error('Error generating PDF:', error);
            alert('Error al generar el PDF: ' + error.message);
        }
    }

    /**
     * Prepara los datos completos del reporte incluyendo columnas y formato
     */
    prepareReportData(reportData) {
        const data = {
            ...reportData,
            // Propiedades esperadas por el template
            companyName: reportData.company || 'Sin especificar',
            reportTitle: reportData.title || 'Reporte',
            reportPeriod: `${reportData.fromDate || ''} al ${reportData.toDate || ''}`,
            generatedDate: new Date().toLocaleString('es-MX')
        };

        // Determinar columnas según el tipo de reporte
        data.columns = this.getColumnsForReport(reportData.title);

        // Preparar filtros
        data.filters = this.prepareFilters(reportData);

        // Convertir filas al formato esperado por el template
        data.rows = this.convertRowsToTableFormat(reportData.rows, data.columns);

        return data;
    }

    /**
     * Obtiene las columnas apropiadas según el tipo de reporte
     */
    getColumnsForReport(reportTitle) {
        switch (reportTitle) {
            case 'Movimientos Auxiliares':
                return [
                    { title: 'Código', isNumber: false },
                    { title: 'Fecha', isNumber: false },
                    { title: 'Nombre', isNumber: false },
                    { title: 'Tipo', isNumber: false },
                    { title: 'Referencia', isNumber: false },
                    { title: 'Saldo Inicial', isNumber: true },
                    { title: 'Débito', isNumber: true },
                    { title: 'Crédito', isNumber: true },
                    { title: 'Balance', isNumber: true }
                ];
            default:
                // Columnas estándar para otros reportes
                return [
                    { title: 'Código', isNumber: false },
                    { title: 'Nombre', isNumber: false },
                    { title: 'Saldo Inicial', isNumber: true },
                    { title: 'Débito', isNumber: true },
                    { title: 'Crédito', isNumber: true },
                    { title: 'Saldo Final', isNumber: true }
                ];
        }
    }

    /**
     * Prepara los filtros para mostrar en el PDF
     */
    prepareFilters(reportData) {
        const filters = [
            { label: 'Compañía', value: reportData.company || 'Sin especificar' },
            { label: 'Sucursal', value: reportData.branch || 'Todas las sucursales' },
            { label: 'Período', value: `${reportData.fromDate || ''} al ${reportData.toDate || ''}` }
        ];

        if (reportData.satNivel) {
            filters.push({ label: 'Nivel SAT', value: reportData.satNivel });
        }

        if (reportData.includeEmpty !== undefined) {
            filters.push({ label: 'Incluir vacías', value: reportData.includeEmpty });
        }

        return filters;
    }

    /**
     * Convierte las filas del reporte al formato de tabla HTML
     */
    convertRowsToTableFormat(rows, columns) {
        if (!rows || !Array.isArray(rows)) return [];

        return rows.map(row => {
            // Crear celdas basadas en las columnas
            const cells = columns.map(column => {
                let value = '';
                let isNumber = column.isNumber;

                switch (column.title) {
                    case 'Código':
                        value = row.code || row.account_code || '';
                        break;
                    case 'Nombre':
                        value = row.name || row.account_name || '';
                        break;
                    case 'Saldo Inicial':
                        value = row.initial_balance || row.balance_inicial || 0;
                        break;
                    case 'Débito':
                        value = row.debit || row.debito || 0;
                        break;
                    case 'Crédito':
                        value = row.credit || row.credito || 0;
                        break;
                    case 'Saldo Final':
                        value = row.ending_balance || row.balance_final || 0;
                        break;
                    default:
                        value = row[column.title.toLowerCase().replace(/\s+/g, '_')] || '';
                }

                return { value, isNumber };
            });

            return {
                cells,
                isGroup: row.isGroup || false,
                level: row.level || 0,
                isTotal: row.isTotal || false,
                isSubtotal: row.isSubtotal || false
            };
        });
    }
}