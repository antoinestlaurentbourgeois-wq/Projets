import UIKit

/// Modèle de facture PDF (format Lettre) : sobre, chaleureux, lisible à l'impression.
enum InvoicePDF {
    struct Theme {
        var name: String
        var main: UIColor
        var soft: UIColor
        var accent: UIColor
    }

    static func rgb(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> UIColor { UIColor(red: r / 255, green: g / 255, blue: b / 255, alpha: 1) }

    static let themes: [String: Theme] = [
        "sarcelle": Theme(name: "Sarcelle", main: rgb(31, 95, 91), soft: rgb(233, 242, 241), accent: rgb(190, 150, 90)),
        "marine": Theme(name: "Bleu marine", main: rgb(36, 58, 99), soft: rgb(234, 238, 246), accent: rgb(183, 146, 74)),
        "prune": Theme(name: "Prune", main: rgb(96, 52, 88), soft: rgb(243, 236, 242), accent: rgb(186, 150, 90)),
        "foret": Theme(name: "Vert forêt", main: rgb(46, 90, 62), soft: rgb(235, 242, 237), accent: rgb(188, 154, 96)),
    ]
    static let themeOrder = ["sarcelle", "marine", "prune", "foret"]

    private static let ink = rgb(38, 44, 52)
    private static let muted = rgb(112, 120, 130)
    private static let hairline = rgb(215, 220, 224)

    private static func font(_ size: CGFloat, bold: Bool = false, italic: Bool = false) -> UIFont {
        let name = bold ? "HelveticaNeue-Bold" : (italic ? "HelveticaNeue-Italic" : "HelveticaNeue")
        return UIFont(name: name, size: size) ?? (bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size))
    }

    static func fileName(_ inv: Invoice) -> String {
        "Facture-\(inv.number)-\(Fr.fileSafe(inv.client.name)).pdf"
    }

    static func data(for inv: Invoice) -> Data {
        // Première passe pour connaître le nombre de pages, seconde pour numéroter « Page x / n ».
        let pages = render(inv, totalPages: 0).pages
        return render(inv, totalPages: pages).data
    }

    // MARK: Rendu

    private static func render(_ inv: Invoice, totalPages: Int) -> (data: Data, pages: Int) {
        let th = themes[inv.provider.theme] ?? themes["sarcelle"]!
        let P = inv.provider, C = inv.client
        let W: CGFloat = 612, H: CGFloat = 792, M: CGFloat = 48, R = W - M, FOOT = H - 54
        let meta: [String: Any] = [
            kCGPDFContextTitle as String: "Facture \(inv.number)",
            kCGPDFContextAuthor as String: P.name,
            kCGPDFContextCreator as String: "Facturation Accompagnement",
        ]
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: W, height: H), format: {
            let f = UIGraphicsPDFRendererFormat(); f.documentInfo = meta; return f
        }())
        var pageCount = 0
        var y: CGFloat = 0

        func draw(_ s: String, x: CGFloat, y: CGFloat, font f: UIFont, color: UIColor = ink,
                  align: NSTextAlignment = .left, kern: CGFloat = 0, width: CGFloat = 400) {
            let style = NSMutableParagraphStyle(); style.alignment = align
            let attrs: [NSAttributedString.Key: Any] = [.font: f, .foregroundColor: color, .paragraphStyle: style, .kern: kern]
            let rect: CGRect
            switch align {
            case .right: rect = CGRect(x: x - width, y: y, width: width, height: 100)
            case .center: rect = CGRect(x: x - width / 2, y: y, width: width, height: 100)
            default: rect = CGRect(x: x, y: y, width: width, height: 100)
            }
            (s as NSString).draw(in: rect, withAttributes: attrs)
        }
        func wrapped(_ s: String, width: CGFloat, font f: UIFont) -> [String] {
            var lines: [String] = []
            for para in s.components(separatedBy: "\n") {
                var current = ""
                for word in para.split(separator: " ", omittingEmptySubsequences: false).map(String.init) {
                    let test = current.isEmpty ? word : current + " " + word
                    if (test as NSString).size(withAttributes: [.font: f]).width > width, !current.isEmpty {
                        lines.append(current); current = word
                    } else { current = test }
                }
                lines.append(current)
            }
            return lines
        }
        func fillRect(_ r: CGRect, _ c: UIColor, radius: CGFloat = 0) {
            c.setFill()
            (radius > 0 ? UIBezierPath(roundedRect: r, cornerRadius: radius) : UIBezierPath(rect: r)).fill()
        }
        func hline(_ y: CGFloat, from x1: CGFloat, to x2: CGFloat, _ c: UIColor, _ w: CGFloat) {
            let p = UIBezierPath(); p.move(to: CGPoint(x: x1, y: y)); p.addLine(to: CGPoint(x: x2, y: y))
            c.setStroke(); p.lineWidth = w; p.stroke()
        }
        func label(_ s: String, x: CGFloat, y: CGFloat, color: UIColor) {
            draw(s.uppercased(), x: x, y: y, font: font(7.5, bold: true), color: color, kern: 1.1)
        }
        func chrome() {
            fillRect(CGRect(x: 0, y: 0, width: W, height: 12), th.main)
            fillRect(CGRect(x: 0, y: 12, width: W, height: 2.5), th.accent)
        }
        func footer() {
            hline(FOOT, from: M, to: R, hairline, 0.6)
            let parts = [P.business.isEmpty ? P.name : P.business, P.phone, P.email].filter { !$0.isEmpty }.joined(separator: "   ·   ")
            draw(parts, x: M, y: FOOT + 8, font: font(8), color: muted, width: 380)
            if totalPages > 0 { draw("Page \(pageCount) / \(totalPages)", x: R, y: FOOT + 8, font: font(8), color: muted, align: .right, width: 100) }
            var ids: [String] = []
            if !P.neq.isEmpty { ids.append("NEQ \(P.neq)") }
            if inv.taxes.enabled { if !P.tpsNo.isEmpty { ids.append("TPS \(P.tpsNo)") }; if !P.tvqNo.isEmpty { ids.append("TVQ \(P.tvqNo)") } }
            if !ids.isEmpty { draw(ids.joined(separator: "   ·   "), x: M, y: FOOT + 19, font: font(8), color: muted, width: 400) }
        }

        let data = renderer.pdfData { ctx in
            func newPage() {
                if pageCount > 0 { footer() }
                ctx.beginPage(); pageCount += 1; chrome(); y = 48
            }
            newPage()

            // En-tête
            y = 52
            draw(P.business.isEmpty ? P.name : P.business, x: M, y: y, font: font(21, bold: true), color: th.main, width: 320)
            var ty = y + 28
            if !P.business.isEmpty && !P.name.isEmpty { draw(P.name, x: M, y: ty, font: font(10), color: muted, width: 320); ty += 15 }
            if !P.tagline.isEmpty { draw(P.tagline, x: M, y: ty, font: font(9.5, italic: true), color: muted, width: 320) }
            draw("FACTURE", x: R, y: y - 4, font: font(28, bold: true), color: th.main, align: .right, kern: 2, width: 240)
            draw("N° \(inv.number)", x: R, y: y + 32, font: font(11, bold: true), align: .right, width: 240)

            // Coordonnées
            y = 134
            let x2 = M + 258, colW: CGFloat = 228
            label("De", x: M, y: y, color: th.accent); label("Facturé à", x: x2, y: y, color: th.accent)
            hline(y + 14, from: M, to: M + 28, th.accent, 0.8); hline(y + 14, from: x2, to: x2 + 28, th.accent, 0.8)
            var ly = y + 24
            draw(P.name, x: M, y: ly, font: font(10.5, bold: true), width: colW); ly += 15
            var left: [String] = []
            if !P.address.isEmpty { left += wrapped(P.address.replacingOccurrences(of: "\n", with: ", "), width: colW, font: font(9.5)) }
            if !P.phone.isEmpty { left.append(P.phone) }
            if !P.email.isEmpty { left.append(P.email) }
            for l in left { draw(l, x: M, y: ly, font: font(9.5), width: colW); ly += 12.5 }

            var ry = y + 24
            let payer = C.billTo.isEmpty ? C.name : C.billTo
            draw(payer, x: x2, y: ry, font: font(10.5, bold: true), width: colW); ry += 15
            var right: [String] = []
            if !C.address.isEmpty { right += wrapped(C.address.replacingOccurrences(of: "\n", with: ", "), width: colW, font: font(9.5)) }
            if let e = C.recipients.first { right.append(e) }
            for l in right { draw(l, x: x2, y: ry, font: font(9.5), width: colW); ry += 12.5 }
            if !C.billTo.isEmpty && C.billTo != C.name {
                ry += 3
                draw("Services rendus à :", x: x2, y: ry, font: font(8.5), color: muted, width: colW); ry += 12
                draw(C.name, x: x2, y: ry, font: font(9.5, bold: true), width: colW); ry += 12.5
            }
            y = max(ly, ry) + 14

            // Bande d'informations
            fillRect(CGRect(x: M, y: y, width: R - M, height: 46), th.soft, radius: 4)
            let cells = [("Date d'émission", Fr.dateLong(inv.date)), ("Échéance", Fr.dateLong(inv.due)),
                         ("Période", String(Fr.periode(inv.periodStart, inv.periodEnd).drop(while: { $0 != " " }).dropFirst()))]
            let cw = (R - M) / 3
            for (i, c) in cells.enumerated() {
                let cx = M + 16 + CGFloat(i) * cw
                label(c.0, x: cx, y: y + 11, color: th.main)
                draw(c.1, x: cx, y: y + 25, font: font(10), width: cw - 22)
            }
            y += 46 + 26

            // Tableau
            let cDate = M + 10, cDesc = M + 108, cQty = R - 168, cRate = R - 92, cAmt = R - 10
            func tableHead() {
                fillRect(CGRect(x: M, y: y, width: R - M, height: 24), th.main, radius: 3)
                let f = font(8, bold: true)
                draw("DATE", x: cDate, y: y + 8, font: f, color: .white, kern: 0.8, width: 90)
                draw("DESCRIPTION", x: cDesc, y: y + 8, font: f, color: .white, kern: 0.8, width: 200)
                draw("QUANTITÉ", x: cQty, y: y + 8, font: f, color: .white, align: .right, kern: 0.8, width: 80)
                draw("TAUX", x: cRate, y: y + 8, font: f, color: .white, align: .right, kern: 0.8, width: 80)
                draw("MONTANT", x: cAmt, y: y + 8, font: f, color: .white, align: .right, kern: 0.8, width: 80)
                y += 24
            }
            tableHead()
            for (i, l) in inv.lines.enumerated() {
                let desc = wrapped(l.desc, width: cQty - 70 - cDesc, font: font(9.5))
                let rowH = max(30, 12 + CGFloat(desc.count) * 12.5 + 5)
                if y + rowH > FOOT - 30 { newPage(); tableHead() }
                if i % 2 == 1 { fillRect(CGRect(x: M, y: y, width: R - M, height: rowH), rgb(248, 249, 250)) }
                let ty = y + 8
                draw(Fr.dateCourte(l.date), x: cDate, y: ty, font: font(9.5, bold: true), width: 95)
                if let s = l.start, let e = l.end {
                    draw("\(Fr.heure(s)) – \(Fr.heure(e))", x: cDate, y: ty + 12, font: font(8), color: muted, width: 95)
                }
                for (k, t) in desc.enumerated() { draw(t, x: cDesc, y: ty + CGFloat(k) * 12.5, font: font(9.5), width: cQty - 70 - cDesc + 10) }
                let q = l.unit == "h" ? Fr.num(l.qty) + " h" : Fr.num(l.qty, 0) + (l.qty > 1 ? " visites" : " visite")
                draw(q, x: cQty, y: ty, font: font(9.5), align: .right, width: 80)
                draw(Fr.money(l.rate) + (l.unit == "h" ? " / h" : ""), x: cRate, y: ty, font: font(9.5), align: .right, width: 80)
                draw(Fr.money(l.amount), x: cAmt, y: ty, font: font(9.5, bold: true), align: .right, width: 80)
                y += rowH
                hline(y, from: M, to: R, hairline, 0.4)
            }

            // Totaux, paiement, notes
            let t = inv.totals
            var rows: [(String, String)] = [("Sous-total", Fr.money(t.subtotal))]
            if inv.taxes.enabled {
                rows.append(("TPS (\(Fr.num(inv.taxes.tps, 0)) %)", Fr.money(t.tps)))
                var tvq = Fr.num(inv.taxes.tvq, 3)
                while tvq.hasSuffix("0") { tvq.removeLast() }
                if tvq.hasSuffix(",") { tvq.removeLast() }
                rows.append(("TVQ (\(tvq) %)", Fr.money(t.tvq)))
            }
            let pay = wrapped(P.payment, width: 232, font: font(9.5))
            let notes = inv.notes.isEmpty ? [] : wrapped(inv.notes, width: 250, font: font(9.5))
            let need = max(CGFloat(rows.count) * 17 + 58, 54 + CGFloat(pay.count) * 12.5 + (notes.isEmpty ? 0 : CGFloat(notes.count) * 12.5 + 30))
            if y + 24 + need > FOOT - 8 { newPage() }
            y += 24
            let top = y, tx = R - 215
            for r in rows {
                draw(r.0, x: tx, y: y, font: font(10), color: muted, width: 120)
                draw(r.1, x: R, y: y, font: font(10), align: .right, width: 100)
                y += 17
            }
            y += 6
            fillRect(CGRect(x: tx - 8, y: y, width: 223, height: 34), th.main, radius: 4)
            draw("TOTAL À PAYER", x: tx + 4, y: y + 13, font: font(8.5, bold: true), color: .white, kern: 0.8, width: 110)
            draw(Fr.money(t.total), x: R - 8, y: y + 8, font: font(15, bold: true), color: .white, align: .right, width: 120)
            let yRight = y + 34

            var ly2 = top
            label("Modalités de paiement", x: M, y: ly2, color: th.accent)
            hline(ly2 + 14, from: M, to: M + 28, th.accent, 0.8)
            ly2 += 24
            draw("Payable avant le \(Fr.dateLong(inv.due)).", x: M, y: ly2, font: font(9.5), width: 240); ly2 += 14
            for l in pay { draw(l, x: M, y: ly2, font: font(9.5), width: 240); ly2 += 12.5 }
            if !notes.isEmpty {
                ly2 += 12; label("Notes", x: M, y: ly2, color: th.accent); ly2 += 14
                for l in notes { draw(l, x: M, y: ly2, font: font(9.5), width: 260); ly2 += 12.5 }
            }
            y = max(yRight, ly2) + 26
            if inv.status == .paid {
                let when = inv.paidAt.map { " le " + Fr.dateLong($0) } ?? ""
                draw("✓ PAYÉE" + when, x: M, y: y, font: font(9, bold: true), color: rgb(46, 125, 80), width: 300); y += 16
            }
            draw("Merci de votre confiance.", x: W / 2, y: min(y + 4, FOOT - 22), font: font(10.5, italic: true), color: th.main, align: .center, width: 300)
            footer()
        }
        return (data, pageCount)
    }
}
