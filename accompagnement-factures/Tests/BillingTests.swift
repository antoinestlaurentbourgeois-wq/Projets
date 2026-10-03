import XCTest
@testable import Factures

final class BillingTests: XCTestCase {
    let cal = Fr.cal

    func date(_ d: Int, _ h: Int = 9, _ m: Int = 0, month: Int = 10) -> Date {
        cal.date(from: DateComponents(year: 2026, month: month, day: d, hour: h, minute: m))!
    }
    func event(_ title: String, _ d: Int, _ h: Int, _ m: Int = 0, mins: Int, calendar: String = "Travail", allDay: Bool = false) -> CalEvent {
        let s = date(d, h, m)
        return CalEvent(key: "\(title)|\(d)|\(h)", title: title, location: "", calendar: calendar, start: s, end: s.addingTimeInterval(Double(mins) * 60), allDay: allDay)
    }

    var clients: [Client] {
        var a = Client(name: "Mme Tremblay", keywords: "Tremblay, Lise"); a.rate = 35; a.travelFee = 5
        var b = Client(name: "Gilles Roy"); b.rate = 40.5
        return [a, b]
    }

    func testNormalisation() {
        XCTAssertEqual(Billing.norm("  Mme  Trémblay-Éloïse! "), " mme tremblay eloise ")
    }

    func testMatchingAvecAccentsEtLePlusLongMotCle() {
        var long = Client(name: "Tremblay Jean", keywords: "Tremblay Jean"); long.rate = 30
        let e = event("TREMBLAY Jean – épicerie", 5, 9, mins: 60)
        let m = Billing.match(e, clients: clients + [long])
        XCTAssertEqual(m?.client.name, "Tremblay Jean")
        XCTAssertEqual(Billing.match(event("Dentiste", 5, 9, mins: 60), clients: clients)?.client.name, nil)
    }

    func testClientInactifOuAutreCalendrierIgnore() {
        var c = clients[0]; c.active = false
        XCTAssertNil(Billing.match(event("Tremblay", 5, 9, mins: 60), clients: [c]))
        c.active = true; c.calendar = "Famille"
        XCTAssertNil(Billing.match(event("Tremblay", 5, 9, mins: 60, calendar: "Travail"), clients: [c]))
        XCTAssertNotNil(Billing.match(event("Tremblay", 5, 9, mins: 60, calendar: "Famille"), clients: [c]))
    }

    func testArrondiEtDureeMinimale() {
        var s = AppSettings(); s.rounding = 15
        XCTAssertEqual(Billing.billableHours(event("x", 5, 9, mins: 80), client: clients[0], rounding: 15), 1.25)
        XCTAssertEqual(Billing.billableHours(event("x", 5, 9, mins: 80), client: clients[0], rounding: 0), 1.33)
        var c = clients[0]; c.minHours = 1
        XCTAssertEqual(Billing.billableHours(event("x", 5, 9, mins: 30), client: c, rounding: 0), 1)
    }

    func testLibelleDeLigne() {
        let s = AppSettings()
        let line = Billing.line(for: event("Mme Tremblay – épicerie", 5, 9, mins: 150), client: clients[0], keyword: "Tremblay", settings: s)
        XCTAssertEqual(line.desc, "Accompagnement – épicerie")
    }

    func testPlanEtTotaux() {
        var s = AppSettings(); s.rounding = 15
        let evs = [event("Mme Tremblay – épicerie", 5, 9, mins: 150), event("Tremblay", 13, 10, mins: 80),
                   event("Gilles Roy", 6, 14, mins: 90), event("Dentiste", 7, 8, mins: 60),
                   event("Vacances Tremblay", 20, 0, mins: 1440, allDay: true),
                   event("Tremblay hors période", 1, 9, mins: 60)]
        var billed = Set<String>(); billed.insert(evs[5].key)
        let plan = Billing.plan(events: evs, clients: clients, settings: s, billed: billed, from: date(2), to: date(31))
        XCTAssertEqual(plan.groups.count, 2)
        XCTAssertEqual(plan.unmatched.map(\.title), ["Dentiste"])
        XCTAssertEqual(plan.allDay, 1)
        let t = plan.groups.first { $0.client.name == "Mme Tremblay" }!
        XCTAssertEqual(t.items.map(\.line.qty), [2.5, 1.25])
        let lines = Billing.withTravel(t.items.map(\.line), client: t.client)
        XCTAssertEqual(lines.last?.amount, 10)             // 2 jours × 5 $
        var tax = TaxSettings(); tax.enabled = true
        let tot = Billing.totals(lines, tax)
        XCTAssertEqual(tot.subtotal, 141.25)
        XCTAssertEqual(tot.tps, 7.06); XCTAssertEqual(tot.tvq, 14.09); XCTAssertEqual(tot.total, 162.40)
        XCTAssertEqual(Billing.totals(lines, TaxSettings()).total, 141.25)
    }

    func testFormatsFrancais() {
        XCTAssertEqual(Fr.money(1234.5), "1 234,50 $")
        XCTAssertEqual(Fr.money(0), "0,00 $")
        XCTAssertEqual(Fr.periode(date(1), date(31)), "de octobre 2026")
        XCTAssertEqual(Fr.periode(date(5), date(19)), "du 5 au 19 octobre 2026")
        XCTAssertEqual(Fr.periode(date(28, month: 9), date(3)), "du 28 septembre 2026 au 3 octobre 2026")
        XCTAssertEqual(Fr.heure(date(5, 9, 5)), "9 h 05")
        XCTAssertEqual(Fr.dateCourte(date(5)), "lun. 5 oct.")
        XCTAssertEqual(Fr.fileSafe("Mme Éloïse Tremblay"), "Mme-Eloise-Tremblay")
    }

    func testNumerotation() {
        var s = AppSettings(); s.prefix = "F-"
        XCTAssertEqual(Billing.nextNumber(s, year: 2026).text, "F-2026-001")
        s.counters["2026"] = 11
        XCTAssertEqual(Billing.nextNumber(s, year: 2026).text, "F-2026-012")
    }

    func testModeleCourriel() {
        var s = AppSettings(); s.provider.name = "Julie"
        let inv = Billing.makeInvoice(client: clients[0], lines: [InvoiceLine(date: date(5), desc: "A", qty: 2, rate: 35)], settings: s, from: date(1), to: date(31), today: date(1, month: 11))
        let out = Billing.fill("{numero} {client} {periode} {total} {echeance} {nom}", invoice: inv)
        XCTAssertEqual(out, "2026-001 Mme Tremblay de octobre 2026 75,00 $ 1er décembre 2026 Julie")
    }
}

final class PDFTests: XCTestCase {
    func makeInvoice(lineCount: Int, taxes: Bool) -> Invoice {
        let cal = Fr.cal
        let base = cal.date(from: DateComponents(year: 2026, month: 9, day: 1, hour: 9))!
        var c = Client(name: "Mme Jeanne Tremblay", billTo: "M. Marc Tremblay", emails: "marc@exemple.ca", address: "123, rue des Érables\nSherbrooke (Québec) J1H 1A1")
        c.rate = 35; c.travelFee = 5
        let lines = (0..<lineCount).map { i -> InvoiceLine in
            let s = cal.date(byAdding: .day, value: i, to: base)!
            return InvoiceLine(key: "k\(i)", date: s, start: s, end: s.addingTimeInterval(9000),
                               desc: i % 3 == 0 ? "Accompagnement – épicerie, pharmacie et dépanneur du quartier avec transport" : "Accompagnement – marche et repas",
                               qty: 2.5, rate: 35)
        }
        var s = AppSettings()
        s.taxes.enabled = taxes
        s.provider = Provider(name: "Julie Gagnon", business: "Accompagnement Julie", address: "45, rue Principale\nSherbrooke (Québec) J1K 2B3", phone: "819 555-0123", email: "julie@exemple.ca", neq: "1234567890", tpsNo: "123456789 RT0001", tvqNo: "1234567890 TQ0001")
        var inv = Billing.makeInvoice(client: c, lines: lines, settings: s, from: base, to: cal.date(from: DateComponents(year: 2026, month: 9, day: 30))!, today: cal.date(from: DateComponents(year: 2026, month: 10, day: 1))!)
        inv.number = "2026-001"; inv.notes = "Merci de régler par virement Interac."
        return inv
    }

    func testPDFUnePageEtPlusieursPages() throws {
        let short = InvoicePDF.data(for: makeInvoice(lineCount: 4, taxes: true))
        let long = InvoicePDF.data(for: makeInvoice(lineCount: 40, taxes: false))
        XCTAssertTrue(String(decoding: short.prefix(5), as: UTF8.self).hasPrefix("%PDF"))
        let d1 = CGPDFDocument(CGDataProvider(data: short as CFData)!)!
        let d2 = CGPDFDocument(CGDataProvider(data: long as CFData)!)!
        XCTAssertEqual(d1.numberOfPages, 1)
        XCTAssertGreaterThan(d2.numberOfPages, 1)
        if let out = ProcessInfo.processInfo.environment["PDF_OUT"] {
            try short.write(to: URL(fileURLWithPath: out + "/exemple-facture.pdf"))
            try long.write(to: URL(fileURLWithPath: out + "/exemple-facture-longue.pdf"))
        }
    }

    func testFichierDansLeDossierDeLApp() {
        let inv = makeInvoice(lineCount: 2, taxes: false)
        let url = FileStorage.save(inv)
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        XCTAssertTrue(url.path.contains("/2026/Mme-Jeanne-Tremblay/Facture-2026-001-"))
        FileStorage.remove(inv)
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }
}
