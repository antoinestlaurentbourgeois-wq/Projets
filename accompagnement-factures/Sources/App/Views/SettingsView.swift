import SwiftUI
import UniformTypeIdentifiers

struct SettingsView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var calendar: CalendarService
    @State private var preview: Data?
    @State private var backup: FileItem?
    @State private var restoring = false
    @State private var message: String?

    private var nextNumber: String { Billing.nextNumber(store.settings, year: Fr.cal.component(.year, from: Date())).text }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Votre nom", text: $store.settings.provider.name)
                    TextField("Nom de l'entreprise (facultatif)", text: $store.settings.provider.business)
                    TextField("Slogan (facultatif)", text: $store.settings.provider.tagline)
                    TextField("Adresse", text: $store.settings.provider.address, axis: .vertical).lineLimit(1...3)
                    TextField("Téléphone", text: $store.settings.provider.phone).keyboardType(.phonePad)
                    TextField("Courriel", text: $store.settings.provider.email).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("NEQ (facultatif)", text: $store.settings.provider.neq)
                } header: { Text("Mes coordonnées") }

                Section {
                    Picker("Style", selection: $store.settings.provider.theme) {
                        ForEach(InvoicePDF.themeOrder, id: \.self) { Text(InvoicePDF.themes[$0]!.name).tag($0) }
                    }
                    Button { preview = InvoicePDF.data(for: sampleInvoice()) } label: { Label("Voir un exemple de facture", systemImage: "doc.richtext") }
                } header: { Text("Modèle de facture PDF") }

                Section {
                    Stepper("Échéance : \(store.settings.dueDays) jours", value: $store.settings.dueDays, in: 0...90, step: 5)
                    Picker("Arrondir la durée", selection: $store.settings.rounding) {
                        Text("Durée exacte").tag(0); Text("Au quart d'heure").tag(15); Text("À la demi-heure").tag(30)
                    }
                    TextField("Libellé par défaut", text: $store.settings.defaultService)
                    TextField("Préfixe du numéro (facultatif)", text: $store.settings.prefix)
                    LabeledContent("Prochain numéro", value: nextNumber)
                    TextEditor(text: $store.settings.provider.payment).frame(minHeight: 80)
                } header: { Text("Facturation") } footer: { Text("Le texte ci-dessus apparaît dans « Modalités de paiement » (ex. adresse Interac).") }

                Section {
                    Toggle("Facturer la TPS et la TVQ", isOn: $store.settings.taxes.enabled)
                    if store.settings.taxes.enabled {
                        HStack { Text("TPS"); Spacer(); TextField("5", value: $store.settings.taxes.tps, format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 80); Text("%") }
                        HStack { Text("TVQ"); Spacer(); TextField("9,975", value: $store.settings.taxes.tvq, format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 80); Text("%") }
                        TextField("N° de TPS", text: $store.settings.provider.tpsNo)
                        TextField("N° de TVQ", text: $store.settings.provider.tvqNo)
                    }
                } header: { Text("Taxes") } footer: { Text("Laissez désactivé si vous n'êtes pas inscrite aux fichiers de taxes.") }

                Section {
                    if calendar.access == .granted {
                        ForEach(calendar.calendars, id: \.calendarIdentifier) { cal in
                            Toggle(cal.title, isOn: Binding(
                                get: { !store.settings.excludedCalendars.contains(cal.calendarIdentifier) },
                                set: { on in
                                    store.settings.excludedCalendars.removeAll { $0 == cal.calendarIdentifier }
                                    if !on { store.settings.excludedCalendars.append(cal.calendarIdentifier) }
                                }))
                        }
                    } else {
                        Text("Accès au calendrier non accordé.").foregroundStyle(.secondary)
                    }
                } header: { Text("Calendriers lus") } footer: { Text("Désactivez les calendriers personnels (anniversaires, famille…) pour ne lire que celui du travail.") }

                Section {
                    Toggle("Préparer les factures chaque mois", isOn: $store.settings.autoDraft)
                    Toggle("Rappel mensuel", isOn: $store.settings.reminder)
                    Stepper("Le \(store.settings.autoDay) du mois", value: $store.settings.autoDay, in: 1...28)
                } header: { Text("Automatisation") } footer: {
                    Text("À l'ouverture de l'app à partir de cette date, les visites du mois précédent sont transformées en factures brouillons, une par client. Rien n'est envoyé sans votre accord : iOS ne permet pas l'envoi automatique de courriels.")
                }

                Section {
                    TextField("Objet", text: $store.settings.subject)
                    TextEditor(text: $store.settings.body).frame(minHeight: 160)
                } header: { Text("Courriel") } footer: {
                    Text("Variables : {numero} {client} {periode} {total} {echeance} {nom}")
                }

                Section {
                    Button("Exporter une sauvegarde") {
                        if let d = store.backupData() {
                            let u = FileManager.default.temporaryDirectory.appendingPathComponent("Sauvegarde-Factures-\(Fr.yearMonth(Date())).json")
                            try? d.write(to: u); backup = FileItem(url: u)
                        }
                    }
                    Button("Restaurer une sauvegarde…") { restoring = true }
                } header: { Text("Données") } footer: {
                    Text("Les données restent sur cet iPhone. Les PDF sont dans Fichiers › Sur mon iPhone › Mes factures.")
                }
            }
            .navigationTitle("Réglages")
            .sheet(isPresented: Binding(get: { preview != nil }, set: { if !$0 { preview = nil } })) {
                PDFPreviewSheet(title: "Exemple de facture", data: preview ?? Data())
            }
            .sheet(item: $backup) { ShareSheet(items: [$0.url]) }
            .fileImporter(isPresented: $restoring, allowedContentTypes: [.json]) { result in
                if case .success(let url) = result {
                    let ok = url.startAccessingSecurityScopedResource()
                    defer { if ok { url.stopAccessingSecurityScopedResource() } }
                    if let d = try? Data(contentsOf: url), store.restore(from: d) { message = "Sauvegarde restaurée." } else { message = "Fichier de sauvegarde illisible." }
                }
            }
            .alert("Sauvegarde", isPresented: Binding(get: { message != nil }, set: { if !$0 { message = nil } })) { Button("OK", role: .cancel) {} } message: { Text(message ?? "") }
        }
    }

    /// Facture fictive pour visualiser le modèle avec les réglages actuels.
    private func sampleInvoice() -> Invoice {
        let cal = Fr.cal
        let base = cal.date(from: DateComponents(year: 2026, month: 9, day: 1, hour: 9))!
        func day(_ d: Int, _ h: Int, _ m: Int, _ dur: Int) -> (Date, Date) {
            let s = cal.date(byAdding: DateComponents(day: d - 1, hour: h - 9, minute: m), to: base)!
            return (s, s.addingTimeInterval(Double(dur) * 60))
        }
        var c = Client(name: "Mme Jeanne Tremblay", billTo: "M. Marc Tremblay", emails: "marc@exemple.ca", address: "123, rue des Érables\nSherbrooke (Québec) J1H 1A1")
        c.rate = 35; c.travelFee = 5
        let items: [(Int, Int, Int, Int, String)] = [(2, 9, 0, 150, "Accompagnement – épicerie et pharmacie"), (9, 13, 30, 120, "Accompagnement – rendez-vous médical"), (16, 9, 0, 150, "Accompagnement – marche et repas"), (23, 14, 0, 90, "Accompagnement – visite et lecture")]
        let lines = items.map { it -> InvoiceLine in
            let (s, e) = day(it.0, it.1, it.2, it.3)
            return InvoiceLine(key: "demo", date: s, start: s, end: e, desc: it.4, qty: Double(it.3) / 60, unit: "h", rate: 35)
        }
        var s = store.settings
        if s.provider.name.isEmpty { s.provider.name = "Votre nom"; s.provider.phone = "819 555-0123"; s.provider.email = "vous@exemple.ca" }
        var inv = Billing.makeInvoice(client: c, lines: lines, settings: s, from: base, to: cal.date(from: DateComponents(year: 2026, month: 9, day: 30))!,
                                      today: cal.date(from: DateComponents(year: 2026, month: 10, day: 1))!)
        inv.number = "2026-001"
        return inv
    }
}
