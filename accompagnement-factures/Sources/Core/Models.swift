import Foundation

/// Un événement lu dans le calendrier de l'iPhone.
struct CalEvent: Identifiable, Hashable {
    var key: String          // identifiant stable : id de l'événement + date de début
    var title: String
    var location: String
    var calendar: String
    var start: Date
    var end: Date
    var allDay: Bool
    var id: String { key }
}

/// Une personne aînée accompagnée (ou la personne qui reçoit la facture à sa place).
struct Client: Identifiable, Codable, Hashable {
    var id = UUID()
    var name = ""               // bénéficiaire des services
    var billTo = ""             // facturé à (ex. un enfant adulte) — vide = le bénéficiaire
    var emails = ""             // un ou plusieurs courriels séparés par des virgules
    var address = ""
    var keywords = ""           // mots du titre d'événement qui désignent ce client
    var calendar = ""           // limiter à un calendrier précis (vide = tous)
    var rate = 35.0             // $ / heure
    var travelFee = 0.0         // $ par jour de visite
    var minHours = 0.0          // durée minimale facturée par visite
    var service = ""            // libellé du service (vide = libellé par défaut)
    var active = true

    var recipients: [String] {
        emails.split(whereSeparator: { ",; \n".contains($0) }).map(String.init).filter { $0.contains("@") }
    }
}

struct TaxSettings: Codable, Hashable {
    var enabled = false
    var tps = 5.0
    var tvq = 9.975
}

/// Coordonnées de la personne qui facture. Copiées dans chaque facture à l'émission.
struct Provider: Codable, Hashable {
    var name = ""
    var business = ""
    var tagline = "Accompagnement et soutien aux aînés"
    var address = ""
    var phone = ""
    var email = ""
    var neq = ""
    var tpsNo = ""
    var tvqNo = ""
    var payment = "Paiement par virement Interac ou chèque.\nMerci d'indiquer le numéro de facture."
    var theme = "sarcelle"
}

struct AppSettings: Codable, Hashable {
    var provider = Provider()
    var taxes = TaxSettings()
    var dueDays = 30
    var rounding = 0                 // minutes : 0 (exact), 15 ou 30
    var defaultService = "Accompagnement"
    var prefix = ""
    var counters: [String: Int] = [:]   // année → dernier numéro utilisé
    var excludedCalendars: [String] = []
    var subject = "Facture {numero} – {periode}"
    var body = "Bonjour,\n\nVeuillez trouver ci-joint la facture {numero} pour les services d'accompagnement rendus {periode} auprès de {client}.\n\nMontant : {total}\nÉchéance : {echeance}\n\nMerci de votre confiance.\n\nCordialement,\n{nom}"
    var autoDraft = true             // crée les brouillons du mois précédent à l'ouverture
    var autoDay = 1                  // jour du mois
    var reminder = true              // rappel mensuel
    var lastAutoPeriod = ""          // « 2026-09 » : dernier mois traité automatiquement
}

enum InvoiceStatus: String, Codable, CaseIterable {
    case draft, sent, paid
    var label: String {
        switch self { case .draft: return "Brouillon"; case .sent: return "Envoyée"; case .paid: return "Payée" }
    }
}

struct InvoiceLine: Identifiable, Codable, Hashable {
    var id = UUID()
    var key = ""                // événement d'origine (vide = ligne manuelle)
    var date: Date
    var start: Date? = nil
    var end: Date? = nil
    var desc: String
    var qty: Double
    var unit = "h"              // « h » ou « visite »
    var rate: Double
    var amount: Double { Money.round2(qty * rate) }
}

struct Invoice: Identifiable, Codable, Hashable {
    var id = UUID()
    var number: String
    var clientID: UUID
    var date: Date
    var due: Date
    var periodStart: Date
    var periodEnd: Date
    var lines: [InvoiceLine]
    var taxes: TaxSettings
    var notes = ""
    var status = InvoiceStatus.draft
    var sentAt: Date? = nil
    var paidAt: Date? = nil
    var provider: Provider
    var client: Client          // copie figée du client à l'émission

    var totals: Totals { Billing.totals(lines, taxes) }
}

struct Totals: Hashable {
    var subtotal: Double
    var tps: Double
    var tvq: Double
    var total: Double
}

enum Money {
    static func round2(_ x: Double) -> Double { (x * 100).rounded() / 100 }
}
