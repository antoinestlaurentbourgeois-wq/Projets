import Foundation

/// Formats français (Québec), indépendants des réglages de l'appareil pour un rendu identique partout.
enum Fr {
    static let mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    static let moisCourt = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    static let joursCourt = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."]

    static var cal: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = .current
        c.firstWeekday = 2
        return c
    }

    private static func parts(_ d: Date) -> DateComponents {
        cal.dateComponents([.year, .month, .day, .hour, .minute, .weekday], from: d)
    }

    static func money(_ v: Double) -> String {
        let cents = Int((abs(v) * 100).rounded())
        let whole = String(cents / 100)
        var grouped = ""
        for (i, ch) in whole.reversed().enumerated() {
            if i > 0 && i % 3 == 0 { grouped.append(" ") }
            grouped.append(ch)
        }
        return (v < 0 ? "-" : "") + String(grouped.reversed()) + "," + String(format: "%02d", cents % 100) + " $"
    }

    static func num(_ v: Double, _ decimals: Int = 2) -> String {
        String(format: "%.\(decimals)f", v).replacingOccurrences(of: ".", with: ",")
    }

    static func dateLong(_ d: Date) -> String {
        let p = parts(d)
        return "\(p.day!)\(p.day == 1 ? "er" : "") \(mois[p.month! - 1]) \(p.year!)"
    }

    static func dateCourte(_ d: Date) -> String {
        let p = parts(d)
        return "\(joursCourt[p.weekday! - 1]) \(p.day!) \(moisCourt[p.month! - 1])"
    }

    static func heure(_ d: Date) -> String {
        let p = parts(d)
        return "\(p.hour!) h " + String(format: "%02d", p.minute!)
    }

    static func moisAnnee(_ d: Date) -> String {
        let p = parts(d)
        return "\(mois[p.month! - 1]) \(p.year!)"
    }

    static func yearMonth(_ d: Date) -> String {
        let p = parts(d)
        return String(format: "%04d-%02d", p.year!, p.month!)
    }

    /// « de octobre 2026 », « du 5 au 19 octobre 2026 », « du 28 septembre 2026 au 3 octobre 2026 ».
    static func periode(_ a: Date, _ b: Date) -> String {
        let pa = parts(a), pb = parts(b)
        if pa.year == pb.year && pa.month == pb.month {
            let last = cal.range(of: .day, in: .month, for: b)!.upperBound - 1
            if pa.day == 1 && pb.day == last { return "de \(mois[pa.month! - 1]) \(pa.year!)" }
            return "du \(pa.day!)\(pa.day == 1 ? "er" : "") au \(dateLong(b))"
        }
        return "du \(dateLong(a)) au \(dateLong(b))"
    }

    static func fileSafe(_ s: String) -> String {
        let folded = s.folding(options: .diacriticInsensitive, locale: nil)
        let cleaned = folded.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) ? Character($0) : "-" }
        let joined = String(cleaned).split(separator: "-").joined(separator: "-")
        return joined.isEmpty ? "client" : joined
    }
}
