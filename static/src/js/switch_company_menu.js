/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { companyService } from "@web/webclient/company_service";

const originalStart = companyService.start; //servicio original

// patch(companyService, {
//     name: "sync_company_group_patch",
//     async start(env, deps) {
//         const service = await originalStart.call(this, env, deps);
//
//         // llamada a metodo original
//         const originalSetCompanies = service.setCompanies.bind(service);
//
//         // extender comportamiento
//         service.setCompanies = async function (companyIds, includeChildCompanies = true) {
//             try {
//                 const orm = env.services.orm;
//                 const user = env.services.user;
//                 const targetCompanyId = companyIds?.[0];
//
//                 if (targetCompanyId) {
//                     const companies = await orm.read("res.company", [targetCompanyId], ["company_group"]);
//                     const companyGroup = companies?.[0]?.company_group;
//
//                     if (companyGroup) {
//                         await orm.write("res.users", [user.userId], { company_group: companyGroup });
//                         console.log("company_group sincronizado:", companyGroup);
//                     }
//                 }
//             } catch (error) {
//                 console.error("Error al sincronizar company_group:", error);
//             }
//
//             // flujo original
//             return originalSetCompanies(companyIds, includeChildCompanies);
//         };
//
//         return service;
//     },
// });

patch(companyService, {
    name: "sync_company_group_patch",
    async start(env, deps) {
        const service = await originalStart.call(this, env, deps);

        const originalSetCompanies = service.setCompanies.bind(service);

        service.setCompanies = async function (companyIds, includeChildCompanies = true) {
            try {
                const orm = env.services.orm;
                const user = env.services.user;
                const targetCompanyId = companyIds?.[0];

                if (targetCompanyId) {
                    // Leer campos relevantes de la compañía seleccionada
                    const companies = await orm.read("res.company", [targetCompanyId], ["company_group", "parent_id"]);
                    const company = companies?.[0];
                    let companyGroup = company?.company_group;

                    // Si no tiene company_group, revisar el parent_id
                    if (!companyGroup && company?.parent_id?.length) {
                        const parentId = company.parent_id[0];
                        const parentCompanies = await orm.read("res.company", [parentId], ["company_group"]);
                        companyGroup = parentCompanies?.[0]?.company_group;
                    }

                    // Si se encontró un company_group (propio o heredado)
                    if (companyGroup) {
                        await orm.write("res.users", [user.userId], { company_group: companyGroup });
                        console.log("✅ company_group sincronizado:", companyGroup);
                    } else {
                        console.log("⚠️ No se encontró company_group ni en la empresa ni en su padre.");
                    }
                }
            } catch (error) {
                console.error("❌ Error al sincronizar company_group:", error);
            }

            // Flujo original
            return originalSetCompanies(companyIds, includeChildCompanies);
        };

        return service;
    },
});