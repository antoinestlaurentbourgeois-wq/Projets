import SwiftUI

struct ClientsView: View {
    @EnvironmentObject var store: Store
    @State private var editing: Client?
    @State private var adding = false

    var body: some View {
        NavigationStack {
            List {
                if store.clients.isEmpty {
                    Section { Text("Aucun client. Touchez + pour ajouter votre premier client.").foregroundStyle(.secondary) }
                }
                ForEach(store.clients) { c in
                    Button { editing = c } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(c.name).font(.headline).foregroundStyle(c.active ? Color.primary : Color.secondary)
                                Text(c.keywords.isEmpty ? "Mot-clé : \(c.name)" : "Mots-clés : \(c.keywords)").font(.footnote).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(Fr.money(c.rate) + " / h").font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                }
                .onDelete { idx in
                    for i in idx { let c = store.clients[i]; store.clients.removeAll { $0.id == c.id } }
                }
            }
            .navigationTitle("Clients")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button { adding = true } label: { Image(systemName: "plus") } } }
            .sheet(item: $editing) { ClientEditView(client: $0, isNew: false) }
            .sheet(isPresented: $adding) { ClientEditView(client: Client(), isNew: true) }
        }
    }
}

struct ClientEditView: View {
    @State var client: Client
    var isNew: Bool
    @EnvironmentObject var store: Store
    @EnvironmentObject var calendar: CalendarService
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Nom de la personne accompagnée", text: $client.name)
                    TextField("Facturé à (si différent)", text: $client.billTo)
                    TextField("Courriel(s) de facturation", text: $client.emails)
                        .keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Adresse", text: $client.address, axis: .vertical).lineLimit(1...3)
                } header: { Text("Identité") } footer: {
                    Text("« Facturé à » : par exemple un fils ou une fille qui reçoit et paie la facture. Plusieurs courriels : séparez-les par une virgule.")
                }
                Section {
                    TextField("Mots du titre du rendez-vous", text: $client.keywords, axis: .vertical).lineLimit(1...3)
                    if !calendar.calendars.isEmpty {
                        Picker("Calendrier", selection: $client.calendar) {
                            Text("Tous les calendriers").tag("")
                            ForEach(calendar.calendars, id: \.calendarIdentifier) { Text($0.title).tag($0.title) }
                        }
                    }
                } header: { Text("Reconnaissance dans le calendrier") } footer: {
                    Text("Chaque événement dont le titre (ou le lieu) contient l'un de ces mots, ou le nom du client, est facturé à ce client. Séparez les mots par des virgules, ex. : Tremblay, Lise T.")
                }
                Section("Tarif") {
                    HStack { Text("Taux horaire"); Spacer(); TextField("0", value: $client.rate, format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 90); Text("$") }
                    HStack { Text("Frais de déplacement / jour"); Spacer(); TextField("0", value: $client.travelFee, format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 90); Text("$") }
                    HStack { Text("Durée minimale / visite"); Spacer(); TextField("0", value: $client.minHours, format: .number).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 90); Text("h") }
                    TextField("Libellé du service (ex. Accompagnement)", text: $client.service)
                }
                Section { Toggle("Client actif", isOn: $client.active) }
            }
            .navigationTitle(isNew ? "Nouveau client" : "Client").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Annuler") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Enregistrer") { store.upsert(client); dismiss() }
                        .disabled(client.name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }
}
