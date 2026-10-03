import Foundation

/// Associe les événements du calendrier aux clients et construit les factures.
enum Billing {
    struct Item: Identifiable {
        var event: CalEvent
        var keyword: String
        var line: InvoiceLine
        var id: String { event.key }
    }

    struct Group: Identifiable {
        var client: Client
        var items: [Item]
        var id: UUID { client.id }
    }

    struct Plan {
        var groups: [Group] = []
        var unmatched: [CalEvent] = []
        var alreadyBilled = 0
        var allDay = 0
    }

    // MARK: Texte

    /// Minuscules, sans accents ni ponctuation, entouré d'espaces (pour chercher des mots entiers).
    static func norm(_ s: String) -> String {
        let folded = s.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "fr_CA"))
        let chars = folded.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) ? Character($0) : " " }
        let words = String(chars).split(separator: " ")
        return " " + words.joined(separator: " ").lowercased() + " "
    }

    static func keywords(of client: Client) -> [String] {
        var list = client.keywords.split(whereSeparator: { ",;\n".contains($0) })
            .map { $0.trimmingCharacters(in: .whitespaces) }
        list.append(client.name.trimmingCharacters(in: .whitespaces))
        return list.filter { norm($0).count >= 4 }   // au moins 2 caractères utiles
    }

    /// Le client dont le mot-clé (le plus long) apparaît dans le titre ou le lieu de l'événement.
    static func match(_ event: CalEvent, clients: [Client]) -> (client: Client, keyword: String)? {
        let haystack = norm(event.title + " " + event.location)
        var best: (client: Client, keyword: String, len: Int)?
        for c in clients where c.active {
            if !c.calendar.isEmpty && norm(c.calendar) != norm(event.calendar) { continue }
            for k in keywords(of: c) {
                let n = norm(k)
                if haystack.contains(n), n.count > (best?.len ?? 0) { best = (c, k, n.count) }
            }
        }
        return best.map { ($0.client, $0.keyword) }
    }

    /// Titre de l'événement sans le nom du client (ex. « Mme Tremblay – épicerie » → « épicerie »).
    static func cleanTitle(_ title: String, removing keyword: String) -> String {
        var t = title
        if let r = t.range(of: keyword, options: [.caseInsensitive, .diacriticInsensitive]) { t.removeSubrange(r) }
        let trim = CharacterSet.whitespaces.union(CharacterSet(charactersIn: "-–—:,.|/"))
        t = t.trimmingCharacters(in: trim)
        while t.contains("  ") { t = t.replacingOccurrences(of: "  ", with: " ") }
        // « Mme » ou « M. » laissé devant le nom retiré
        if let r = t.range(of: "^(mme|madame|monsieur|mr|m)\\.?\\s+", options: [.regularExpression, .caseInsensitive]) { t.removeSubrange(r) }
        return t.trimmingCharacters(in: trim)
    }

    // MARK: Montants

    static func billableHours(_ event: CalEvent, client: Client, rounding: Int) -> Double {
        var minutes = event.end.timeIntervalSince(event.start) / 60
        if rounding > 0 { minutes = (minutes / Double(rounding)).rounded() * Double(rounding) }
        var hours = minutes / 60
        if client.minHours > 0 && hours < client.minHours { hours = client.minHours }
        return Money.round2(hours)
    }

    static func line(for event: CalEvent, client: Client, keyword: String, settings: AppSettings) -> InvoiceLine {
        let base = client.service.isEmpty ? settings.defaultService : client.service
        let extra = cleanTitle(event.title, removing: keyword)
        let desc = (!extra.isEmpty && norm(extra) != norm(base)) ? "\(base) – \(extra)" : base
        return InvoiceLine(key: event.key, date: event.start, start: event.start, end: event.end, desc: desc,
                           qty: billableHours(event, client: client, rounding: settings.rounding),
                           unit: "h", rate: client.rate)
    }

    /// Ajoute (ou met à jour) la ligne « Frais de déplacement » : un forfait par jour de visite.
    static func withTravel(_ lines: [InvoiceLine], client: Client) -> [InvoiceLine] {
        var out = lines.filter { $0.unit != "visite" }
        let visits = out.filter { $0.unit == "h" }
        guard client.travelFee > 0, let last = visits.last else { return out }
        let days = Set(visits.map { Fr.yearMonth($0.date) + "-\(Fr.cal.component(.day, from: $0.date))" }).count
        out.append(InvoiceLine(key: "dep|" + last.key, date: last.date, desc: "Frais de déplacement",
                               qty: Double(days), unit: "visite", rate: client.travelFee))
        return out
    }

    static func totals(_ lines: [InvoiceLine], _ taxes: TaxSettings) -> Totals {
        let sub = Money.round2(lines.reduce(0) { $0 + $1.amount })
        let tps = taxes.enabled ? Money.round2(sub * taxes.tps / 100) : 0
        let tvq = taxes.enabled ? Money.round2(sub * taxes.tvq / 100) : 0
        return Totals(subtotal: sub, tps: tps, tvq: tvq, total: Money.round2(sub + tps + tvq))
    }

    static func nextNumber(_ settings: AppSettings, year: Int) -> (text: String, n: Int) {
        let n = (settings.counters[String(year)] ?? 0) + 1
        return (settings.prefix + String(year) + "-" + String(format: "%03d", n), n)
    }

    // MARK: Plan de facturation

    static func plan(events: [CalEvent], clients: [Client], settings: AppSettings,
                     billed: Set<String>, from: Date, to: Date) -> Plan {
        var plan = Plan()
        let cal = Fr.cal
        let endExclusive = cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: to))!
        var groups: [UUID: Group] = [:]
        for ev in events where ev.start >= cal.startOfDay(for: from) && ev.start < endExclusive {
            if ev.allDay { plan.allDay += 1; continue }
            if billed.contains(ev.key) { plan.alreadyBilled += 1; continue }
            guard let m = match(ev, clients: clients) else { plan.unmatched.append(ev); continue }
            let item = Item(event: ev, keyword: m.keyword, line: line(for: ev, client: m.client, keyword: m.keyword, settings: settings))
            groups[m.client.id, default: Group(client: m.client, items: [])].items.append(item)
        }
        plan.groups = groups.values.map { g in
            var g = g; g.items.sort { $0.event.start < $1.event.start }; return g
        }.sorted { $0.client.name.localizedCaseInsensitiveCompare($1.client.name) == .orderedAscending }
        plan.unmatched.sort { $0.start < $1.start }
        return plan
    }

    // MARK: Création

    static func makeInvoice(client: Client, lines: [InvoiceLine], settings: AppSettings,
                            from: Date, to: Date, today: Date = Date()) -> Invoice {
        let cal = Fr.cal
        let year = cal.component(.year, from: today)
        let num = nextNumber(settings, year: year)
        let all = withTravel(lines.sorted { $0.date < $1.date }, client: client)
        return Invoice(number: num.text, clientID: client.id, date: today,
                       due: cal.date(byAdding: .day, value: settings.dueDays, to: today)!,
                       periodStart: from, periodEnd: to, lines: all, taxes: settings.taxes,
                       provider: settings.provider, client: client)
    }

    /// Premier et dernier jour du mois contenant `date`.
    static func monthRange(of date: Date) -> (Date, Date) {
        let cal = Fr.cal
        let start = cal.date(from: cal.dateComponents([.year, .month], from: date))!
        let end = cal.date(byAdding: DateComponents(month: 1, day: -1), to: start)!
        return (start, end)
    }

    static func fill(_ template: String, invoice: Invoice) -> String {
        template
            .replacingOccurrences(of: "{numero}", with: invoice.number)
            .replacingOccurrences(of: "{client}", with: invoice.client.name)
            .replacingOccurrences(of: "{periode}", with: Fr.periode(invoice.periodStart, invoice.periodEnd))
            .replacingOccurrences(of: "{total}", with: Fr.money(invoice.totals.total))
            .replacingOccurrences(of: "{echeance}", with: Fr.dateLong(invoice.due))
            .replacingOccurrences(of: "{nom}", with: invoice.provider.name)
    }
}
