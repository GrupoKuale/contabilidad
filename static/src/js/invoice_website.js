let cpDictionary = {};
let _coloniasActuales = [];


document.addEventListener('DOMContentLoaded', () => {
    console.log('its a good day')



    window.initBranchDropdown = function () {
        const dropdown = document.getElementById('branchDropdown');
        const trigger = document.getElementById('branchTrigger');

        if (!trigger || trigger.dataset.initialized) return;
        trigger.dataset.initialized = 'true';

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdown.classList.toggle('is-open');
        });

        document.addEventListener('click', (e) => {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('is-open');
            }
        });
    };

    window.goBackToCompanies = function () {
        document.getElementById('email-notice-page').classList.add('d-none');
        document.getElementById('page1').classList.remove('d-none');
    };

    window.selectCompany = function selectCompany(element) {
        const companyId = element.getAttribute('data-id');

        localStorage.setItem('selected_company_id', companyId)
        //console.log("Compañía seleccionada con ID:", companyId);
        //updateCompanyImage(companyId);

        updateTicketImage(companyId);

        // 2️⃣ Inicializar trigger
        initBranchDropdown();
        loadBranches(companyId);

        const now = new Date();
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);

        flatpickr("#date", {
            locale: "es",
            dateFormat: "Y-m-d",
            altFormat: "d/m/Y",
            allowInput: false,
            disableMobile: true,
            appendTo: document.body,
            minDate: firstDay,
            maxDate: lastDay,
            onReady: function (selectedDates, dateStr, instance) {
                instance.calendarContainer.classList.add('kuale-calendar');
            }
        });
    }

    window.goBack = function goBack() {
        // Encuentra la página actual que NO está oculta
        const pages = document.querySelectorAll('.form-page');
        let currentPageIndex = -1;

        pages.forEach((page, index) => {
            if (!page.classList.contains('d-none')) {
                currentPageIndex = index;
            }
        });

        // Si hay una página anterior, oculta la actual y muestra la anterior
        if (currentPageIndex > 0) {
            pages[currentPageIndex].classList.add('d-none');
            pages[currentPageIndex - 1].classList.remove('d-none');
        }
    };

    window.continueToStep2 = function continueToStep2() {
        var complaintType = document.getElementById("complaint_type").value;

        if (complaintType) {
            document.getElementById("step1").style.display = "none";
            document.getElementById("step2").style.display = "block";

            var complaintText =
                document.getElementById("complaint_type").options[document.getElementById("complaint_type").selectedIndex].text;
            document.getElementById("selected_problem_text").innerHTML = "<strong>" + complaintText + "</strong>";


        } else {
            showError("Por favor selecciona un tipo de problema.");
        }
    }

    window.goToNextPage = function goToNextPage() {
        const branchId = window._selectedBranchId;
        if (branchId) {
        } else {
            showError('Por favor, selecciona una sucursal.');
        }
    }

    window._selectedBranchId = null; // valor accesible globalmente
    window.loadBranches = async function loadBranches(company_id) {

        const menu = document.getElementById('branchMenu');
        const label = document.getElementById('branchLabel');
        const dropdown = document.getElementById('branchDropdown');

        if (!menu || !label || !dropdown) {
            console.warn('loadBranches: elementos no encontrados en el DOM');
            return;
        }

        const resetDropdown = (text) => {
            menu.innerHTML = '';
            label.textContent = text;
            label.classList.remove('has-value');
            dropdown.classList.remove('is-open');
            window._selectedBranchId = null;
        };

        if (!company_id) {
            resetDropdown('Seleccione una sucursal');
            return;
        }

        try {
            const response = await fetch('/get_branches', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ company_id: company_id })
            });

            const data = await response.json();
            console.log("Respuesta del backend:", data);

            if (data.status === 200) {

                if (data.facturaCorreo) {
                    console.log('es tinto')
                    document.getElementById('page1').classList.add('d-none');
                    document.getElementById('email-notice-page').classList.remove('d-none');
                    return;
                }

                document.getElementById('page1').classList.add('d-none');
                document.getElementById('page2').classList.remove('d-none');

                resetDropdown('Seleccione una sucursal');

                data.data.forEach(branch => {
                    const div = document.createElement('div');
                    div.className = 'kuale-state-dropdown__option';
                    div.dataset.value = branch.id;
                    div.textContent = branch.name;

                    div.addEventListener('click', () => {
                        menu.querySelectorAll('.kuale-state-dropdown__option')
                            .forEach(o => o.classList.remove('is-selected'));

                        div.classList.add('is-selected');
                        label.textContent = branch.name;
                        label.classList.add('has-value');
                        dropdown.classList.remove('is-open');

                        // Guardar el valor seleccionado
                        window._selectedBranchId = branch.id;
                        window._selectedBranchCP = branch.cp_branch || null;

                        // Ejecutar la lógica que antes estaba en onchange
                        goToNextPage();
                    });

                    menu.appendChild(div);
                });

            } else {
                resetDropdown('No hay sucursales disponibles');
            }

        } catch (error) {
            console.error('Error:', error);
            resetDropdown('Error al cargar sucursales');
        }
    };

    window.goToPage3 = async function goToPage3() {
        const branchId = window._selectedBranchId;
        const ticket = document.getElementById('ticket').value;
        const date = document.getElementById('date').value;
        const amount = document.getElementById('amount').value;

        if (!branchId || !ticket || !date || !amount) {
            showError('Por favor, completa todos los campos antes de continuar.');
            return;
        }

        // Guardar los datos en localStorage
        localStorage.setItem('branchId', branchId);
        localStorage.setItem('ticket', ticket);
        localStorage.setItem('date', date);
        localStorage.setItem('amount', amount);

        try {
            const tInfo = {
                ticket_folio: ticket,
                branch_id: branchId,
                date: date,
                amount: parseFloat(amount) // Lo convierte a número
            };

            const preResponse = await fetch('/validate/ticket', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(tInfo)
            });

            const preData = await preResponse.json();

            if (preResponse.ok && preData.status === 200) {
                window.ticketId = preData.data[0].id;
                window.ticketPaymentClave = preData.data[0].payment_type_clave;
                window.ticketPaymentDescripcion = preData.data[0].payment_type_descripcion;

                if (preData.data[0].invoiced) {
                    console.log("Ticket facturado");
                    goToPage(5);
                } else {
                    console.log("Ticket no facturado");
                    document.getElementById('page2').classList.add('d-none');
                    document.getElementById('page3').classList.remove('d-none');
                }
            } else {
                console.error("Ticket no encontrado o error en validación:", preData.message || preData.status);
                showError(preData.message || "No se encontró el ticket, revisa los datos e intenta nuevamente.");
            }

        } catch (error) {
            console.error("Error al hacer la solicitud:", error);
            showError("Ocurrió un error al validar el ticket. Intenta nuevamente.");
        }
    };

    window.goToPage4 = function goToPage4() {
        // Obtener los valores ingresados en la página 3
        const rfc = document.getElementById('rfc').value;
        const receiver = document.getElementById('receiver').value;
        const address = document.getElementById('address').value;
        const taxRegime = document.getElementById('tax_regime').value;
        const cfdiUse = document.getElementById('cfdi_use').value;
        const clientEmail = document.getElementById('client_email').value;

        // Validar campos obligatorios
        if (!rfc || !receiver || !address || !taxRegime || !cfdiUse || !clientEmail) {
            showError('Por favor, completa todos los campos antes de continuar.');
            return;
        }

        // Validar RFC genérico con "Público en general"
        if (rfc.toUpperCase() === 'XAXX010101000' && esPublicoEnGeneral(receiver)) {
            showError('El RFC genérico no puede tener "Público en general" como nombre.');
            return;
        }

        // Guardar en localStorage
        localStorage.setItem('rfc', rfc);
        localStorage.setItem('receiver', receiver);
        localStorage.setItem('address', address);
        localStorage.setItem('taxRegime', taxRegime);
        localStorage.setItem('cfdiUse', cfdiUse);
        localStorage.setItem('clientEmail', clientEmail);

        if (document.getElementById('extra-address').checked) {
            const state = document.getElementById('address-state').value;
            const city = document.getElementById('address-city').value;
            const street1 = document.getElementById('address-st1').value;
            const street2 = document.getElementById('address-st2').value;
            const extNumber = document.getElementById('address-extNumber').value;
            const intNumber = document.getElementById('address-intNumber').value;
            if (!state || !city || !street1 || !street2 || !extNumber || !intNumber) {
                showError('Por favor, completa todos los campos antes de continuar.');
                return;
            }
            localStorage.setItem('extraAddress', true)
            localStorage.setItem('extraAddressState', state);
            localStorage.setItem('extraAddressCity', city);
            localStorage.setItem('extraAddressStreet1', street1);
            localStorage.setItem('extraAddressStreet2', street2);
            localStorage.setItem('extraAddressExtNumber', extNumber);
            localStorage.setItem('extraAddressIntNumber', intNumber);
        }


        // Ir a la página 4
        document.getElementById("page3").classList.add("d-none");
        document.getElementById("page4").classList.remove("d-none");

        // Llamar a la función que muestra los datos en los recuadros
        displayInvoiceData();
    }

    window.displayInvoiceData = function displayInvoiceData() {
        const branchName = document.getElementById('branchLabel')?.textContent ||
            localStorage.getItem('branchId') ||
            'No disponible';

        // Obtener texto del régimen seleccionado
        const taxRegimeEl = document.getElementById('tax_regime');
        const taxRegimeVal = localStorage.getItem('taxRegime') || '';
        const taxRegimeOpt = taxRegimeEl
            ? Array.from(taxRegimeEl.options).find(o => o.value === taxRegimeVal)
            : null;
        const taxRegimeText = taxRegimeOpt
            ? taxRegimeOpt.textContent.trim()  // ← solo el texto
            : taxRegimeVal || 'No disponible';

        // Obtener texto del uso CFDI seleccionado
        const cfdiUseEl = document.getElementById('cfdi_use');
        const cfdiUseVal = localStorage.getItem('cfdiUse') || '';
        const cfdiUseOpt = cfdiUseEl
            ? Array.from(cfdiUseEl.options).find(o => o.value === cfdiUseVal)
            : null;
        const cfdiUseText = cfdiUseOpt
            ? cfdiUseOpt.textContent.trim()  // ← solo el texto, sin concatenar el valor
            : cfdiUseVal || 'No disponible';

        document.getElementById('summary-branch').textContent = branchName;
        document.getElementById('summary-branch').textContent = branchName || branchId || 'No disponible';
        document.getElementById('summary-ticket').textContent = localStorage.getItem('ticket') || 'No disponible';
        document.getElementById('summary-date').textContent = localStorage.getItem('date') || 'No disponible';
        document.getElementById('summary-amount').textContent = localStorage.getItem('amount') || 'No disponible';
        document.getElementById('summary-rfc').textContent = localStorage.getItem('rfc') || 'No disponible';
        document.getElementById('summary-receiver').textContent = localStorage.getItem('receiver') || 'No disponible';
        document.getElementById('summary-address').textContent = localStorage.getItem('address') || 'No disponible';
        document.getElementById('summary-taxRegime').textContent = taxRegimeText;
        document.getElementById('summary-cfdiUse').textContent = cfdiUseText;
        document.getElementById('summary-clientEmail').textContent = localStorage.getItem('clientEmail') || 'No disponible';
        document.getElementById('summary-paymentType').textContent = window.ticketPaymentClave && window.ticketPaymentDescripcion
        ? `${window.ticketPaymentClave} - ${window.ticketPaymentDescripcion}`
        : 'No disponible';
    }

    window.goToPage = function goToPage(pageNumber) {
        // Ocultar todas las páginas
        document.querySelectorAll('.form-page').forEach(page => {
            page.classList.add('d-none');
        });

        // Mostrar la página deseada
        document.getElementById(`page${pageNumber}`).classList.remove('d-none');
    }

    window.clearInvoiceForm = function clearInvoiceForm() {
        const fieldIds = [
            'ticket', 'date', 'amount', 'rfc', 'receiver', 'address',
            'tax_regime', 'cfdi_use', 'client_email',
            'address-state', 'address-city', 'address-st1', 'address-st2',
            'address-extNumber', 'address-intNumber', 'email_invoice_client'
        ];
        fieldIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });

        const extraAddress = document.getElementById('extra-address');
        if (extraAddress) {
            extraAddress.checked = false;
            toggleAddressFields();
        }

        const branchLabel = document.getElementById('branchLabel');
        if (branchLabel) {
            branchLabel.textContent = 'Seleccione una sucursal';
            branchLabel.classList.remove('has-value');
        }
        window._selectedBranchId = null;
        window._selectedBranchCP = null;

        const storageKeys = [
            'branchId', 'ticket', 'date', 'amount', 'rfc', 'receiver', 'address',
            'taxRegime', 'cfdiUse', 'clientEmail', 'extraAddress',
            'extraAddressState', 'extraAddressCity', 'extraAddressStreet1',
            'extraAddressStreet2', 'extraAddressExtNumber', 'extraAddressIntNumber'
        ];
        storageKeys.forEach(key => localStorage.removeItem(key));

        window.ticketId = null;
    };

    window.startNewInvoice = function startNewInvoice() {
        window.clearInvoiceForm();
        window.goToPage(1);
    };

    window.submitInvoiceData = async function submitInvoiceData() {
        // 1. Instanciar y mostrar el modal con Vanilla JS
        const loadingModalElement = document.getElementById('loadingModal');
        const loadingModal = bootstrap.Modal.getOrCreateInstance(loadingModalElement);
        loadingModal.show();

        // Asegurar que el spinner y el mensaje de carga sean visibles
        document.getElementById('loadingSpinner').classList.remove('d-none');
        document.getElementById('errorMessage').classList.add('d-none');
        document.getElementById('closeModalBtn').classList.add('d-none');

        const rfcIngresado = document.getElementById('rfc').value;
        const RFC_GENERICO = 'XAXX010101000';

        const data = {
            // ... (tus variables de data se quedan exactamente igual)
            company_id: localStorage.getItem('selected_company_id'),
            branch_id: window._selectedBranchId,
            ticket: document.getElementById('ticket').value,
            date: document.getElementById('date').value,
            amount: document.getElementById('amount').value ?
                parseFloat(document.getElementById('amount').value) : null,
            rfc: document.getElementById('rfc').value,
            receiver: document.getElementById('receiver').value,
            address: rfcIngresado === RFC_GENERICO && window._selectedBranchCP
                ? window._selectedBranchCP
                : document.getElementById('address').value,
            tax_regime: document.getElementById('tax_regime').value,
            cfdi_use: document.getElementById('cfdi_use').value,
            client_email: document.getElementById('client_email').value,
        };

        if (document.getElementById('extra-address').checked) {
            data.extra_address = {
                state: localStorage.getItem('extraAddressState'),
                city: localStorage.getItem('extraAddressCity'),
                street01: localStorage.getItem('extraAddressStreet1'),
                street02: localStorage.getItem('extraAddressStreet2'),
                ext_number: localStorage.getItem('extraAddressExtNumber'),
                int_number: localStorage.getItem('extraAddressIntNumber'),
            }
        }

        try {
            const response = await fetch('/invoice/data', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (result.status === 200) {
                // 2. Ocultar el modal con Vanilla JS
                loadingModal.hide();
                goToPage(5);
            } else {
                console.log('Error', result);
                throw new Error(result.message || 'Error desconocido al procesar la factura.');
            }
        } catch (error) {
            console.error('Error:', error);

            // Ocultar el spinner y mostrar el mensaje de error dentro del modal
            document.getElementById('loadingSpinner').classList.add('d-none');
            document.getElementById('errorMessage').innerText = error.message;
            document.getElementById('errorMessage').classList.remove('d-none');
            document.getElementById('closeModalBtn').classList.remove('d-none');
        }
    };

    window.filterOptionsByRfc = function filterOptionsByRfc() {
        const rfcInput = document.getElementById('rfc').value.trim();
        const taxRegimeSelect = document.getElementById('tax_regime');
        const cfdiUseSelect = document.getElementById('cfdi_use');
        const isMoral = rfcInput.length === 12;
        const isFisica = rfcInput.length === 13;
        Array.from(taxRegimeSelect.options).forEach(option => {
            const moral = option.getAttribute('data-moral') === 'True';
            const fisica = option.getAttribute('data-fisica') === 'True';
            if ((isMoral && moral) || (isFisica && fisica)) {
                option.style.display = ''; // Mostrar opción
            } else {
                option.style.display = 'none'; // Ocultar opción
            }
        });
        if (!isMoral && !isFisica && rfcInput.length > 0) {
            console.warn('El RFC no es válido. Debe tener 12 caracteres para personas morales o 13 para físicas.');
        }

        Array.from(cfdiUseSelect.options).forEach(option => {
            const moral = option.getAttribute('data-moral') === 'True';
            const fisica = option.getAttribute('data-fisica') === 'True';
            const clave = option.getAttribute('data-clave');
            if ((isMoral && moral && clave === 'G03') || (isFisica && fisica && clave === 'S01')) {
                option.style.display = ''; // Mostrar opción
            } else {
                option.style.display = 'none'; // Ocultar opción
            }
        });
        if (!isMoral && !isFisica && rfcInput.length > 0) {
            console.warn('El RFC no es válido. Debe tener 12 caracteres para personas morales o 13 para físicas.');
        }
    }

    document.getElementById('rfc').addEventListener('input', filterOptionsByRfc);

    window.openComplaintForm = function openComplaintForm() {
        const modal = new bootstrap.Modal(document.getElementById('complaintModal'));
        modal.show();
    }

    window.submitComplaint = function submitComplaint() {
        // Obtener valores de los campos del formulario
        const complaintType = document.getElementById('complaint_type').value;
        const rfc = document.getElementById('rfc2').value;
        const receiver = document.getElementById('receiver2').value;
        const taxRegime = document.getElementById('tax_regime2').value;
        const cfdiUse = document.getElementById('cfdi_use2').value;
        const email = document.getElementById('email').value;
        const invoiceFile = document.getElementById('invoice').files[0];
        const ticketFile = document.getElementById('ticket_t').files[0];
        const numTicket = document.getElementById('numTicket2').value;
        const empresa = document.getElementById('company2').value;
        const sucursal = document.getElementById('branch2').value;
        const cp = document.getElementById('cp2').value;




        // Validar que los campos de texto obligatorios no estén vacíos
        const requiredFields = {
            'Tipo de problema': complaintType,
            'RFC': rfc,
            'Nombre': receiver,
            'Régimen Fiscal': taxRegime,
            'Uso de CFDI': cfdiUse,
            'Correo': email,
            'Foto Ticket': ticketFile,
            'Numero Ticket': numTicket,
            'Empresa': empresa,
            'Sucursal': sucursal,
            'Codigo Postal': cp
        };

        const missing = Object.keys(requiredFields).filter(key => !requiredFields[key]);

        if (missing.length > 0) {
            showError("Por favor, complete los siguientes campos: " + missing.join(', '));
            return;
        }

        // Los archivos son opcionales según el diseño, pero si quieres forzar al menos uno:
        /*
        if (!invoiceFile && !ticketFile) {
            showError("Por favor, adjunte al menos un archivo (Constancia o Ticket).");
            return;
        }
        */

        // Crear un objeto FormData para enviar archivos y datos del formulario
        const formData = new FormData();
        formData.append('complaint_type', complaintType);
        formData.append('rfc', rfc);
        formData.append('cp', cp);
        formData.append('receiver', receiver);
        formData.append('tax_regime', taxRegime);
        formData.append('cfdi_use', cfdiUse);
        formData.append('email', email);
        formData.append('invoice', invoiceFile);
        formData.append('ticket_t', ticketFile);
        formData.append('numticket', numTicket);
        formData.append('empresa', empresa);
        formData.append('sucursal', sucursal);


        // Realizar la solicitud POST
        fetch('/create_invoice_complaint_ticket', {
            method: 'POST',
            body: formData,
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === 200) {
                    showError(data.message);
                    // Cerrar el modal después de enviar exitosamente
                    const modal = bootstrap.Modal.getInstance(document.getElementById('complaintModal'));
                    modal.hide();
                } else {
                    showError("Error: " + data.message);
                }
            })
            .catch(error => {
                console.error('Error al enviar el formulario:', error);
                showError('Ocurrió un error al enviar el formulario.');
            });
    }

    window.sendInvoiceByEmail = async function sendInvoiceByEmail() {
        console.log('send invoice email');

        const email = document.getElementById('email_invoice_client').value.trim();

        // Validación de email
        if (!email || !/^\S+@\S+\.\S+$/.test(email)) {
            Swal.fire({
                icon: 'warning',
                title: 'Correo inválido',
                text: 'Por favor, ingrese un correo electrónico válido.',
            });
            return;
        }

        const data = {
            ticket_folio: document.getElementById('ticket').value,
            email: email,
            company_id: localStorage.getItem('selected_company_id'),
            branch_id: localStorage.getItem('branchId'),
            date: localStorage.getItem('date'),
            amount: localStorage.getItem('amount'),
        };

        try {
            const response = await fetch('/send_email_to', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });

            const result = await response.json();

            if (result.status === 200) {
                Swal.fire({
                    icon: 'success',
                    title: 'Factura enviada',
                    text: 'La factura ha sido enviada exitosamente al correo proporcionado.',
                    confirmButtonText: 'Aceptar',
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error al enviar',
                    text: 'Hubo un problema al enviar la factura. Intente nuevamente más tarde.',
                });
            }
        } catch (error) {
            console.error('Error en la solicitud:', error);
            Swal.fire({
                icon: 'error',
                title: 'Error de conexión',
                text: 'No se pudo conectar con el servidor. Verifique su conexión a internet.',
            });
        }
    };


    window.searchRFC = function searchRFC() {
        console.log('rfc search');
        let rfc = document.getElementById('rfc').value.trim();

        if (!rfc || rfc.length > 13 || rfc.length < 12) {
            showError('Por favor, ingresa un RFC válido.');
            return;
        }

        fetch('/search/by/rfc/' + rfc, { method: 'GET' })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showError(data.error);
                    return;
                }

                document.getElementById('receiver').value = data.name || '';
                document.getElementById('address').value = data.zip || '';
                document.getElementById('client_email').value = data.email || '';

                // Seleccionar régimen por valor (no por texto)
                const taxRegimeEl = document.getElementById('tax_regime');
                const matchingOpt = Array.from(taxRegimeEl.options)
                    .find(o => o.value === data.tax_regime);
                if (matchingOpt) taxRegimeEl.value = matchingOpt.value;

                // Filtrar CFDI según régimen
                filtrarCFDIUse(
                    document.getElementById('cfdi_use'),
                    data.tax_regime || ''
                );

                // ← Llenar estado, municipio y colonias
                const cp = data.zip || '';
                if (cp.length === 5) buscarCP(cp);
            })
            .catch(error => console.error('Error:', error));
    };

    window.searchRFC2 = function searchRFC2() {
        console.log('rfc search')
        let rfc = document.getElementById("rfc2").value.trim();
        if (!rfc || rfc.length > 13 || rfc.length < 12) {
            showError("Por favor, ingresa un RFC válido.");
            return;
        }

        fetch('/search/by/rfc/' + rfc, {
            method: 'GET'
        }).then(response => response.json())
            .then(data => {
                if (data.error) {
                    showError(data.error);
                } else {
                    // Llenar los campos con los datos obtenidos
                    document.getElementById("receiver2").value = data.name || "";
                    document.getElementById("tax_regime2").value = data.tax_regime || "";
                    document.getElementById("cfdi_use2").value = data.cfdi_use || "";
                    document.getElementById("email").value = data.email || "";
                }
            }).catch(error => console.error('Error: ', error))

    }

    const usosPorDefecto = ['G03', 'S01'];
    const clavesUsosPorDefecto = ['G03 - Gastos en general', 'S01 - Sin efectos fiscales'];

    window.filtrarCFDIUse = function filtrarCFDIUse(selectUso, claveRegimen) {
        // Limpia TODAS las opciones del foreach de la vista
        selectUso.innerHTML = '<option value=""></option>';

        if (claveRegimen === '605' || claveRegimen === '616') {
            // Reglas 2 y 3 — solo S01
            const opt = document.createElement('option');
            opt.value = 'S01';
            opt.textContent = 'S01 - Sin efectos fiscales';
            selectUso.appendChild(opt);
            selectUso.value = 'S01'; // se selecciona automáticamente

        } else {
            // Regla 1 — solo G03 y S01
            usosPorDefecto.forEach((val, i) => {
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = clavesUsosPorDefecto[i];
                selectUso.appendChild(opt);
            });
        }
    }

    window.previewFile = function previewFile(inputId) {
        const input = document.getElementById(inputId);
        const preview = document.getElementById(inputId + '-preview');
        const fileName = document.getElementById(inputId + '-name');

        if (input.files && input.files[0]) {
            fileName.textContent = input.files[0].name;
            preview.classList.remove('d-none');
        }
    }

    window.updateTicketImage = async function updateTicketImage(companyId) {
        const ticketImage = document.getElementById("ticket-image");
        const imageElement = document.getElementById("company-image");

        try {
            const response = await fetch('/get_img_ticket', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ company_id: companyId })
            });

            const data = await response.json();
            console.log("Respuesta del backend img:", data);

            if (data.status === 200) {
                ticketImage.src = data.ticket_image;

                imageElement.src = data.company_image;
                imageElement.classList.remove("d-none"); // Oculta la imagen si no hay una asignada

            } else {
                ticketImage.src = "/contabilidad_kuale/static/src/img/ejemplo_ticket.png"; // Imagen por defecto si no hay una asignada
                imageElement.classList.add("d-none"); // Oculta la imagen si no hay una asignada
            }
        } catch (error) {
            console.error('Error:', error);
            ticketImage.src = "/contabilidad_kuale/static/src/img/ejemplo_ticket.png";
        }
    }

    window.updateCompanyImage = function updateCompanyImage(companyId) {
        const imageElement = document.getElementById("company-image");

        // Definir las rutas de las imágenes según el ID de la empresa
        const images = {
            160: "/contabilidad_kuale/static/src/img/Logo DQ.svg",
            159: "/contabilidad_kuale/static/src/img/Logo Tinto.svg",
            158: "/contabilidad_kuale/static/src/img/Logo Carls Jr.svg"
        };

        if (images[companyId]) {
            imageElement.src = images[companyId];  // Cambia la imagen
            imageElement.classList.remove("d-none"); // Muestra la imagen
        } else {

        }
    }

    window.downloadXML = function downloadXML() {
        if (!window.ticketId) {
            showError('No hay ticket validado');
            return;
        }

        fetch('/download_xml/' + window.ticketId, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/xml',
            }
        })
            .then(async response => {
                if (response.ok) {
                    const blob = await response.blob();
                    const contentDisposition = response.headers.get('Content-Disposition');
                    let filename = 'factura.xml';
                    if (contentDisposition) {
                        const filenameStarMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
                        if (filenameStarMatch) {
                            filename = decodeURIComponent(filenameStarMatch[1]);
                        } else {
                            const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
                            if (filenameMatch) filename = filenameMatch[1];
                        }
                    }
                    var link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = filename;
                    link.click();
                } else {
                    throw new Error('Error al descargar el archivo');
                }
            })
            .catch(error => {
                showError('No se pudo descargar el archivo: ' + error.message);
            });
    }

    window.downloadPDF = function downloadPDF() {
        if (!window.ticketId) {
            showError('No hay ticket validado');
            return;
        }

        fetch('/download_pdf/' + window.ticketId, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/pdf',
            }
        })
            .then(async response => {
                if (response.ok) {
                    const blob = await response.blob();
                    const contentDisposition = response.headers.get('Content-Disposition');
                    let filename = 'factura.pdf';
                    if (contentDisposition) {
                        const filenameStarMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
                        if (filenameStarMatch) {
                            filename = decodeURIComponent(filenameStarMatch[1]);
                        } else {
                            const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
                            if (filenameMatch) filename = filenameMatch[1];
                        }
                    }
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = filename;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    window.open(url, '_blank');
                } else {
                    throw new Error('Error al descargar el archivo');
                }
            })
            .catch(error => {
                showError('No se pudo descargar el archivo: ' + error.message);
            });
    }

    window.handleFileUpload = function handleFileUpload(file) {
        if (file.type !== 'application/pdf') {
            showError('Solo se permiten archivos PDF.');
            return;
        }

        const formData = new FormData();
        formData.append('pdf', file);

        fetch('/upload', {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === 200) {
                    populateFormFields(data.data);
                } else {
                    showError('Error al procesar el archivo: ' + data.message);
                }
            })
            .catch(error => {
                showError('Error al procesar el archivo.');
                console.error(error);
            });
    }

    window.populateFormFields = function populateFormFields(data) {
        document.getElementById('rfc').value = data['RFC'] || '';
        document.getElementById('receiver').value = data['Nombre o Razón Social'] || '';
        document.getElementById('address').value = data['Código Postal'] || '';

        const taxRegimeSelect = document.getElementById('tax_regime');
        const regimenfiscal = data['Régimen Fiscal'] || '';

        Array.from(taxRegimeSelect.options).forEach(option => {
            // Comparar si el texto de la opción contiene la descripción recibida
            if (option.textContent.trim().includes(regimenfiscal.trim())) {
                taxRegimeSelect.value = option.value;
            }
        });

        filterOptionsByRfc();

        filtrarCFDIUse(
            document.getElementById('cfdi_use'),
            taxRegimeSelect.value
        );

        //Busca estado, municipio y colonia
        const cp = data['Código Postal'] || '';
        if (cp.length === 5) buscarCP(cp);
    };

    window.showError = function showError(message) {
        const spinner = document.getElementById('loadingSpinner');
        const errorMsg = document.getElementById('errorMessage');
        const closeBtn = document.getElementById('closeModalBtn');

        // Cambiar jQuery por Bootstrap Vanilla JS
        const loadingModalElement = document.getElementById('loadingModal');
        const loadingModal = bootstrap.Modal.getOrCreateInstance(loadingModalElement);
        loadingModal.show();

        spinner.classList.add('d-none');
        errorMsg.innerText = message;
        errorMsg.classList.remove('d-none');
        closeBtn.classList.remove('d-none');
    }

    //PROBLEMAS DE FACTURACION

    window.loadBranches2 = async function (company_id) {
        const select = document.getElementById('branch2');

        if (!select) return;

        // Resetear
        select.innerHTML = '<option value="">Seleccione una sucursal</option>';

        if (!company_id) return;

        try {
            const response = await fetch('/get_branches', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ company_id: company_id })
            });

            const data = await response.json();

            if (data.status === 200) {
                data.data.forEach(branch => {
                    const option = document.createElement('option');
                    option.value = branch.id;
                    option.textContent = branch.name;
                    select.appendChild(option);
                });
            } else {
                select.innerHTML = '<option value="">No hay sucursales disponibles</option>';
            }

        } catch (error) {
            console.error('Error en loadBranches2:', error);
            select.innerHTML = '<option value="">Error al cargar sucursales</option>';
        }
    };












    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('upload-pdf');
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragging');
    });
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragging');
    });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragging');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            handleFileUpload(fileInput.files[0]);
        }
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileUpload(fileInput.files[0]);
        }
    });


    // Agregar el evento para detectar cambios en el checkbox
    document.getElementById("extra-address").addEventListener("change", toggleAddressFields);

    document.getElementById("btn_send_email_invoice").addEventListener('click', (e) => {
        e.preventDefault()
        sendInvoiceByEmail()
    })

    // Cargar datos almacenados al cargar la página
    window.onload = function () {
        if (localStorage.getItem('extraAddressChecked') === 'true') {
            document.getElementById('extra-address').checked = true;
            toggleAddressFields();
        }
    };

    //filtrar usos de CFDI
    const taxRegimeEl = document.getElementById('tax_regime');
    const cfdiUseEl = document.getElementById('cfdi_use');

    if (taxRegimeEl && cfdiUseEl) {
        taxRegimeEl.addEventListener('change', () => {
            filtrarCFDIUse(cfdiUseEl, taxRegimeEl.value);
        });
    }

    if (taxRegimeEl) {
        Array.from(taxRegimeEl.options).forEach(opt => {
            if (opt.value) opt.textContent = `${opt.value} - ${opt.textContent.trim()}`;
        });
    }

    window.esPublicoEnGeneral = function esPublicoEnGeneral(texto) {
        const normalizado = texto
            .toLowerCase()
            .normalize('NFD')                          // descompone acentos
            .replace(/[\u0300-\u036f]/g, '')           // elimina acentos
            .replace(/[^a-z0-9\s]/g, '')               // elimina caracteres especiales
            .replace(/\s+/g, ' ')                      // normaliza espacios
            .trim();

        const variantes = [
            'publico en general',
            'público en general',
            'pub en general',
            'p en general',
            'publico gral',
            'pub gral',
        ];

        return variantes.some(v => normalizado.includes(v));
    }

    window.filtrarRegimenFiscal = function filtrarRegimenFiscal(selectRegimen, rfc) {
        const isGenerico = rfc === 'XAXX010101000';

        if (isGenerico) {
            // Ocultar todas y mostrar solo 616
            Array.from(selectRegimen.options).forEach(opt => {
                opt.style.display = opt.value === '616' ? '' : 'none';
            });
            selectRegimen.value = '616';
        } else {
            // Mostrar todas y dejar que filterOptionsByRfc filtre según longitud
            Array.from(selectRegimen.options).forEach(opt => {
                opt.style.display = '';
            });
            filterOptionsByRfc();
        }
    }


    //validacion de rfc generico con publico en general
    const rfcInput = document.getElementById('rfc');

    if (rfcInput) {
        rfcInput.addEventListener('blur', () => {
            const rfc = rfcInput.value.trim().toUpperCase();
            const receiver = document.getElementById('receiver').value.trim().toLowerCase();
            const taxRegimeSelect = document.getElementById('tax_regime');
            const cfdiUseSelect = document.getElementById('cfdi_use');

            if (rfc === 'XAXX010101000' && esPublicoEnGeneral(receiver)) {
                showError('El RFC genérico no puede tener "Público en general" como nombre.');
                document.getElementById('receiver').value = '';
                return;
            }

            filtrarRegimenFiscal(taxRegimeSelect, rfc);
            filtrarCFDIUse(cfdiUseSelect, taxRegimeSelect.value);
        });
    }





    loadCPData();

    // Focus en colonia → mostrar todas las opciones
    const coloniaInput = document.getElementById('address-st2');
    if (coloniaInput) {
        coloniaInput.addEventListener('focus', () => {
            if (_coloniasActuales.length > 0) {
                renderColonias(_coloniasActuales);
            }
        });
    }

    // Cerrar dropdown de colonia al hacer click fuera
    document.addEventListener('click', (e) => {
        const menu = document.getElementById('coloniaMenu');
        const input = document.getElementById('address-st2');
        if (menu && input && !input.contains(e.target) && !menu.contains(e.target)) {
            menu.classList.remove('visible');
        }
    });




});

//FUNCIONALIDAD DE CODIGO POSTAL DINAMICO

window.loadCPData = async function () {
    try {
        const response = await fetch('/contabilidad_kuale/static/src/SAT_Catalogo/cp_data.json');
        cpDictionary = await response.json();
        console.log('✅ CP cargado:', Object.keys(cpDictionary).length, 'códigos postales');
    } catch (error) {
        console.error('Error al cargar CP:', error);
    }
};

window.buscarCP = function (cp) {
    const resultado = cpDictionary[String(cp).padStart(5, '0')];

    if (!resultado) {
        console.warn('CP no encontrado:', cp);
        return;
    }

    const stateEl = document.getElementById('address-state');
    const cityEl = document.getElementById('address-city');
    if (stateEl) stateEl.value = resultado.estado;
    if (cityEl) cityEl.value = resultado.municipio;

    llenarColonias(resultado.colonias);
};

window.llenarColonias = function (colonias) {
    _coloniasActuales = colonias;
    const coloniaInput = document.getElementById('address-st2');
    if (coloniaInput) coloniaInput.value = '';
    renderColonias(colonias);
};


function renderColonias(lista) {
    const menu = document.getElementById('coloniaMenu');
    if (!menu) return;

    menu.innerHTML = '';

    if (lista.length === 0) {
        menu.classList.remove('visible');
        return;
    }

    lista.forEach(colonia => {
        const div = document.createElement('div');
        div.className = 'kuale-state-dropdown__option';
        div.textContent = colonia;

        div.addEventListener('click', () => {
            document.getElementById('address-st2').value = colonia;
            menu.classList.remove('visible');
        });

        menu.appendChild(div);
    });

    menu.classList.add('visible');
}

window.filtrarColonias = function (texto) {
    const menu = document.getElementById('coloniaMenu');
    if (!menu) return;

    if (!texto.trim()) {
        renderColonias(_coloniasActuales);
        return;
    }

    const filtradas = _coloniasActuales.filter(c =>
        c.toLowerCase().includes(texto.toLowerCase())
    );

    renderColonias(filtradas);
};

window.toggleAddressFields = function toggleAddressFields() {
    const addressExtraFields = document.getElementById('address-extra-fields');
    const extraAddressChecked = document.getElementById('extra-address').checked;

    if (extraAddressChecked) {
        addressExtraFields.style.display = 'block';

        const cpInput = document.getElementById('address');
        if (cpInput && !cpInput.dataset.cpInitialized) {
            cpInput.dataset.cpInitialized = 'true';

            let cpTimer = null;
            cpInput.addEventListener('input', () => {
                clearTimeout(cpTimer);
                cpTimer = setTimeout(() => {
                    const cp = cpInput.value.trim();
                    if (cp.length === 5) buscarCP(cp);
                }, 400);
            });
        }

        const cp = document.getElementById('address').value.trim();
        if (cp.length === 5) buscarCP(cp);

    } else {
        addressExtraFields.style.display = 'none';
    }
};

// ── CHATBOT CON RESPUESTAS PREDEFINIDAS ───────────────────

const CASOS = [
    {
        keywords: ['ticket no existe', 'no existe el ticket', 'ticket invalido', 'ticket inválido', 'no encuentra el ticket', 'ticket no encontrado', 'no existe ticket'],
        respuesta: 'Para generar tu factura es necesario que adjuntes tus datos fiscales y la imagen de tu ticket para poder apoyarte.'
    },
    {
        keywords: ['nombre del receptor', 'nombre receptor', 'nombre no coincide', 'nombre incorrecto', 'razon social no coincide', 'razon social no corresponde', 'nombre no corresponde'],
        respuesta: 'Es necesario que verifiques dentro de tu constancia de situación fiscal que los datos sean correctos y los captures correctamente, o bien arrastra tu constancia en el 3er paso del formulario para que se llene la información automáticamente. Si el problema persiste, adjunta tus datos fiscales y la imagen de tu ticket para apoyarte.'
    },
    {
        keywords: ['domicilio fiscal', 'codigo postal incorrecto', 'cp incorrecto', 'domicilio incorrecto', 'domicilio no coincide', 'domicilio no corresponde'],
        respuesta: 'Es necesario que verifiques dentro de tu constancia de situación fiscal que los datos sean correctos y los captures correctamente, o bien arrastra tu constancia en el 3er paso del formulario para que se llene la información automáticamente. Si el problema persiste, adjunta tus datos fiscales y la imagen de tu ticket para apoyarte.'
    },
    {
        keywords: ['forma de pago no corresponde', 'pago no corresponde', 'comprobante de pago', 'forma pago no es correcta', 'forma pago incorrecta', 'metodo de pago incorrecto'],
        respuesta: 'Para generar tu factura es necesario que adjuntes tus datos fiscales, la imagen de tu ticket y el comprobante de pago para poder apoyarte.'
    },
    {
        keywords: ['regimen incorrecto', 'regimen fiscal incorrecto', 'regimen equivocado', 'regimen mal', 'regimen fiscal mal'],
        respuesta: 'Se realizará una sustitución de tu factura. Para ello es necesario que adjuntes tus datos fiscales y la imagen de tu ticket o tu factura.'
    },
    {
        keywords: ['forma de pago de mi factura', 'factura forma de pago', 'factura pago incorrecto', 'factura con pago incorrecto', 'pago de mi factura incorrecto'],
        respuesta: 'Se realizará una sustitución de tu factura. Para ello es necesario que adjuntes tus datos fiscales, la imagen de tu ticket o tu factura y el comprobante de pago.'
    },
    {
        keywords: ['razon social incorrecta', 'equivoque razon social', 'razon social equivocada', 'nombre equivocado en factura', 'factura nombre incorrecto', 'me equivoque de razon', 'razon social mal'],
        respuesta: 'Se realizará una nueva factura. Para ello es necesario que adjuntes tus datos fiscales y la imagen de tu ticket o tu factura.'
    },
    {
        keywords: ['reenviar factura', 'no me llego', 'no me llegó', 'no aparece en correo', 'no recibi factura', 'no recibí factura', 'mandar factura', 'enviar factura', 'factura al correo', 'no aparece factura'],
        respuesta: 'Favor de proporcionar el número de ticket, la sucursal y un correo electrónico para reenviar tu factura a la brevedad.'
    },
];

function detectarCaso(texto) {
    const t = texto.toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9\s]/g, ' ')
        .trim();

    for (const caso of CASOS) {
        if (caso.keywords.some(kw => t.includes(kw))) {
            return caso.respuesta;
        }
    }
    return null;
}

window.toggleChat = function () {
    const chat = document.getElementById('kualeChat');
    chat.classList.toggle('is-open');
    if (chat.classList.contains('is-open')) {
        document.getElementById('chatInput').focus();
    }
};

window.sendMessage = function () {
    const input = document.getElementById('chatInput');
    const mensaje = input.value.trim();
    if (!mensaje) return;

    input.value = '';
    input.disabled = true;

    appendMessage(mensaje, 'user');

    const typingId = appendTyping();

    setTimeout(() => {
        removeTyping(typingId);

        const respuesta = detectarCaso(mensaje);

        if (respuesta) {
            appendMessage(respuesta, 'bot');
        } else {
            appendMessage(
                'Para poder apoyarte mejor, ¿podrías describir con más detalle el problema que tienes con tu factura? Por ejemplo: "el ticket no existe", "mi factura tiene un régimen incorrecto", "no me llegó mi factura al correo", etc.',
                'bot'
            );
        }

        input.disabled = false;
        input.focus();
    }, 600);
};

function appendMessage(texto, tipo) {
    const messages = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = `kuale-chat__msg kuale-chat__msg--${tipo}`;
    div.innerHTML = `<p>${texto}</p>`;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function appendTyping() {
    const messages = document.getElementById('chatMessages');
    const id = 'typing-' + Date.now();
    const div = document.createElement('div');
    div.className = 'kuale-chat__msg kuale-chat__msg--typing';
    div.id = id;
    div.innerHTML = '<p>Escribiendo...</p>';
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return id;
}

function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

//CUANDO SE ABRE LA VENTANA DE CHATBOT SE CIERRA EL DIALOGO
window.toggleChat = function () {
    const chat = document.getElementById('kualeChat');
    const fab = document.getElementById('chatFab');
    chat.classList.toggle('is-open');

    if (chat.classList.contains('is-open')) {
        fab.classList.add('chat-open');
        document.getElementById('chatInput').focus();
    } else {
        fab.classList.remove('chat-open');
    }
};



