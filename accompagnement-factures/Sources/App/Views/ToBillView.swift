import SwiftUI

/// Lit le calendrier de l'iPhone et propose, client par client, les visites à facturer.
struct ToBillView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var calendar: CalendarService
    @EnvironmentObject var router: Router
    @Environment(\.openURL) private var openURL

    @State private var mode = 0                      // 0 : mois précédent, 1 : ce mois-ci, 2 : dates au choix
    @State private var customFrom = Fr.cal.date(byAdding: .day, value: -14, to: Date())!
    @State private var customTo = Date()
    @State private var plan = Billing.Plan()
    @State private var excluded = Set<String>()
    @State private var created: Invoice?
    @State private var newClient: Client?

    private var range: (Date, Date) {
        switch mode {
        case 0: return Billing.monthRange(of: Fr.cal.date(byAdding: .month, value: -1, to: Date())!)
        case 1: return Billing.monthRange(of: Date())
        default: return (min(customFrom, customTo), max(customFrom, customTo))
        }
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("Période", selection: $mode) {
                        Text("Mois dernier").tag(0); Text("Ce mois-ci").tag(1); Text("Dates").tag(2)
                    }.pickerStyle(.segmented)
                    if mode == 2 {
                        DatePicker("Du", selection: $customFrom, displayedComponents: .date)
                        DatePicker("Au", selection: $customTo, displayedComponents: .date)
                    }
                } footer: {
                    Text("Visites du \(Fr.dateLong(range.0)) au \(Fr.dateLong(range.1)), lues dans votre calendrier.")
                }

                if calendar.access != .granted { permission }
                else if store.clients.isEmpty { emptyClients }
                else {
                    ForEach(plan.groups) { group in groupSection(group) }
                    if plan.groups.isEmpty { Section { Label("Rien à facturer pour cette période.", systemImage: "checkmark.circle").foregroundStyle(.secondary) } footer: { skipped } }
                    else { Section { } footer: { skipped } }
                    if !plan.unmatched.isEmpty { unmatchedSection }
                }
            }
            .navigationTitle("À facturer")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Tout créer") { createAll() }.disabled(plan.groups.allSatisfy { selected($0).isEmpty })
                }
            }
            .refreshable { reload() }
            .onAppear { reload() }
            .onChange(of: mode) { _, _ in reload() }
            .onChange(of: customFrom) { _, _ in reload() }
            .onChange(of: customTo) { _, _ in reload() }
            .onChange(of: store.clients) { _, _ in reload() }
            .onChange(of: store.invoices.count) { _, _ in reload() }
            .onChange(of: calendar.access) { _, _ in reload() }
            .onChange(of: store.settings.excludedCalendars) { _, _ in reload() }
            .onChange(of: store.settings.rounding) { _, _ in reload() }
            .sheet(item: $created) { inv in InvoiceDetailView(invoiceID: inv.id).environmentObject(store) }
            .sheet(item: $newClient) { c in ClientEditView(client: c, isNew: true) }
        }
    }

    // MARK: Sections

    private var permission: some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                Label("Accès au calendrier requis", systemImage: "calendar").font(.headline)
                Text("L'app lit votre calendrier Apple pour retrouver les visites. Rien n'est modifié ni envoyé ailleurs.").font(.subheadline).foregroundStyle(.secondary)
                if calendar.access == .unknown {
                    Button("Autoriser l'accès") { Task { await calendar.requestAccess() } }.buttonStyle(.borderedProminent)
                } else {
                    Button("Ouvrir les Réglages de l'iPhone") { if let u = URL(string: UIApplication.openSettingsURLString) { openURL(u) } }.buttonStyle(.borderedProminent)
                    Text("Réglages › Confidentialité › Calendriers › Factures › Accès complet").font(.footnote).foregroundStyle(.secondary)
                }
            }.padding(.vertical, 4)
        }
    }

    private var emptyClients: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                Label("Ajoutez d'abord vos clients", systemImage: "person.badge.plus").font(.headline)
                Text("Pour chaque aîné, indiquez un mot qui apparaît dans le titre de ses rendez-vous (ex. « Tremblay »). L'app reliera ensuite chaque visite du calendrier au bon client.").font(.subheadline).foregroundStyle(.secondary)
                Button("Ajouter un client") { router.tab = .clients }.buttonStyle(.borderedProminent)
            }.padding(.vertical, 4)
        }
    }

    private func selected(_ g: Billing.Group) -> [Billing.Item] { g.items.filter { !excluded.contains($0.event.key) } }

    private func groupSection(_ g: Billing.Group) -> some View {
        let sel = selected(g)
        let lines = Billing.withTravel(sel.map(\.line), client: g.client)
        let total = Billing.totals(lines, store.settings.taxes).total
        return Section {
            ForEach(g.items) { item in
                Button {
                    if excluded.contains(item.event.key) { excluded.remove(item.event.key) } else { excluded.insert(item.event.key) }
                } label: {
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: excluded.contains(item.event.key) ? "circle" : "checkmark.circle.fill")
                            .foregroundStyle(excluded.contains(item.event.key) ? Color.secondary : Color.accentColor).font(.title3)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.event.title).foregroundStyle(.primary)
                            Text("\(Fr.dateCourte(item.event.start)) · \(Fr.heure(item.event.start)) – \(Fr.heure(item.event.end))").font(.footnote).foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(Fr.num(item.line.qty) + " h").foregroundStyle(.primary)
                            Text(Fr.money(item.line.amount)).font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Button {
                create(g)
            } label: {
                HStack { Image(systemName: "doc.badge.plus"); Text("Créer la facture · \(Fr.money(total))"); Spacer() }.fontWeight(.semibold)
            }.disabled(sel.isEmpty)
        } header: {
            Text("\(g.client.name) — \(sel.count) visite\(sel.count > 1 ? "s" : "")")
        }
    }

    private var unmatchedSection: some View {
        Section {
            ForEach(plan.unmatched) { ev in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(ev.title)
                        Text("\(Fr.dateCourte(ev.start)) · \(Fr.heure(ev.start)) – \(Fr.heure(ev.end))").font(.footnote).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Menu("Associer") {
                        ForEach(store.clients.filter(\.active)) { c in
                            Button(c.name) { store.addKeyword(ev.title, to: c.id) }
                        }
                        Button("Nouveau client…") { newClient = Client(name: "", keywords: ev.title) }
                    }.font(.subheadline)
                }
            }
        } header: { Text("Sans client reconnu (\(plan.unmatched.count))") } footer: {
            Text("Ces événements ne contiennent le nom d'aucun client. Associez-les à un client pour qu'ils soient facturés, ou ignorez-les s'ils sont personnels.")
        }
    }

    private var skipped: some View {
        let parts = [plan.alreadyBilled > 0 ? "\(plan.alreadyBilled) visite(s) déjà facturée(s)" : nil,
                     plan.allDay > 0 ? "\(plan.allDay) événement(s) « toute la journée » ignoré(s)" : nil].compactMap { $0 }
        return Text(parts.joined(separator: " · "))
    }

    // MARK: Actions

    private func reload() {
        guard calendar.access == .granted else { plan = Billing.Plan(); return }
        let (a, b) = range
        let events = calendar.events(from: a, to: b, excluded: store.settings.excludedCalendars)
        plan = Billing.plan(events: events, clients: store.clients, settings: store.settings, billed: store.billedKeys, from: a, to: b)
    }

    private func create(_ g: Billing.Group) {
        let (a, b) = range
        created = store.createInvoice(client: g.client, lines: selected(g).map(\.line), from: a, to: b)
    }

    private func createAll() {
        let (a, b) = range
        var n = 0
        for g in plan.groups where !selected(g).isEmpty {
            store.createInvoice(client: g.client, lines: selected(g).map(\.line), from: a, to: b); n += 1
        }
        if n > 0 { router.notice = "\(n) facture\(n > 1 ? "s créées" : " créée") en brouillon. Vérifiez-les puis envoyez-les depuis l'onglet Factures."; router.tab = .invoices }
    }
}
