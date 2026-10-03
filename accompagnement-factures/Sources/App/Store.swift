import Foundation
import SwiftUI

/// Toutes les données de l'app (clients, factures, réglages) : un fichier JSON local, sauvegardé à chaque changement.
@MainActor
final class Store: ObservableObject {
    struct Snapshot: Codable {
        var clients: [Client] = []
        var invoices: [Invoice] = []
        var settings = AppSettings()
    }

    @Published var clients: [Client] = [] { didSet { save() } }
    @Published var invoices: [Invoice] = [] { didSet { save() } }
    @Published var settings = AppSettings() { didSet { save() } }

    private var loading = true
    private let fileURL: URL = {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("donnees.json")
    }()

    init() {
        let dec = JSONDecoder()
        if let d = try? Data(contentsOf: fileURL), let s = try? dec.decode(Snapshot.self, from: d) {
            clients = s.clients; invoices = s.invoices; settings = s.settings
        }
        loading = false
    }

    private func save() {
        guard !loading else { return }
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let d = try? enc.encode(Snapshot(clients: clients, invoices: invoices, settings: settings)) {
            try? d.write(to: fileURL, options: .atomic)
        }
    }

    // MARK: Sauvegarde / restauration

    func backupData() -> Data? {
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try? enc.encode(Snapshot(clients: clients, invoices: invoices, settings: settings))
    }

    func restore(from data: Data) -> Bool {
        guard let s = try? JSONDecoder().decode(Snapshot.self, from: data) else { return false }
        clients = s.clients; invoices = s.invoices; settings = s.settings
        return true
    }

    // MARK: Clients

    func client(_ id: UUID) -> Client? { clients.first { $0.id == id } }

    func upsert(_ c: Client) {
        if let i = clients.firstIndex(where: { $0.id == c.id }) { clients[i] = c } else { clients.append(c) }
        clients.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    func addKeyword(_ word: String, to clientID: UUID) {
        guard var c = client(clientID) else { return }
        let w = word.trimmingCharacters(in: .whitespaces)
        guard !w.isEmpty else { return }
        c.keywords = c.keywords.isEmpty ? w : c.keywords + ", " + w
        upsert(c)
    }

    // MARK: Factures

    /// Clés des événements déjà facturés (pour ne jamais facturer deux fois la même visite).
    var billedKeys: Set<String> {
        Set(invoices.flatMap { $0.lines.map(\.key) }.filter { !$0.isEmpty })
    }

    @discardableResult
    func createInvoice(client: Client, lines: [InvoiceLine], from: Date, to: Date) -> Invoice {
        var inv = Billing.makeInvoice(client: client, lines: lines, settings: settings, from: from, to: to)
        let year = Fr.cal.component(.year, from: inv.date)
        let n = (settings.counters[String(year)] ?? 0) + 1
        settings.counters[String(year)] = n
        inv.number = settings.prefix + String(year) + "-" + String(format: "%03d", n)
        invoices.insert(inv, at: 0)
        FileStorage.save(inv)
        return inv
    }

    func update(_ inv: Invoice) {
        guard let i = invoices.firstIndex(where: { $0.id == inv.id }) else { return }
        FileStorage.remove(invoices[i])
        invoices[i] = inv
        FileStorage.save(inv)
    }

    func delete(_ inv: Invoice) {
        FileStorage.remove(inv)
        invoices.removeAll { $0.id == inv.id }
    }

    func mark(_ inv: Invoice, _ status: InvoiceStatus) {
        var x = inv
        x.status = status
        if status == .sent { x.sentAt = Date() }
        if status == .paid { x.paidAt = Date(); if x.sentAt == nil { x.sentAt = Date() } }
        if status == .draft { x.sentAt = nil; x.paidAt = nil }
        update(x)
    }

    // MARK: Automatisation mensuelle

    /// Crée des brouillons pour le mois précédent (une fois par mois, à partir du jour choisi).
    /// Retourne le nombre de factures créées.
    @discardableResult
    func autoDraftIfDue(events: [CalEvent], today: Date = Date()) -> Int {
        guard settings.autoDraft else { return 0 }
        let cal = Fr.cal
        guard cal.component(.day, from: today) >= settings.autoDay else { return 0 }
        let prev = cal.date(byAdding: .month, value: -1, to: today)!
        let tag = Fr.yearMonth(prev)
        guard settings.lastAutoPeriod != tag else { return 0 }
        let (a, b) = Billing.monthRange(of: prev)
        let plan = Billing.plan(events: events, clients: clients, settings: settings, billed: billedKeys, from: a, to: b)
        for g in plan.groups { createInvoice(client: g.client, lines: g.items.map(\.line), from: a, to: b) }
        settings.lastAutoPeriod = tag
        return plan.groups.count
    }
}
