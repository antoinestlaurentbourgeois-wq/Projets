import Foundation

/// Enregistre chaque facture en PDF dans le dossier de l'app, visible dans l'app Fichiers :
/// Fichiers › Sur mon iPhone › Mes factures › AAAA › Nom du client.
enum FileStorage {
    static var root: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    static func url(for inv: Invoice) -> URL {
        let year = String(Fr.cal.component(.year, from: inv.date))
        return root.appendingPathComponent(year, isDirectory: true)
            .appendingPathComponent(Fr.fileSafe(inv.client.name), isDirectory: true)
            .appendingPathComponent(InvoicePDF.fileName(inv))
    }

    @discardableResult
    static func save(_ inv: Invoice) -> URL {
        let u = url(for: inv)
        try? FileManager.default.createDirectory(at: u.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? InvoicePDF.data(for: inv).write(to: u, options: .atomic)
        return u
    }

    static func remove(_ inv: Invoice) {
        try? FileManager.default.removeItem(at: url(for: inv))
    }

    /// Copie temporaire pour le partage / l'envoi (toujours à jour avec la dernière version de la facture).
    static func temporaryCopy(_ inv: Invoice) -> URL {
        let u = FileManager.default.temporaryDirectory.appendingPathComponent(InvoicePDF.fileName(inv))
        try? InvoicePDF.data(for: inv).write(to: u, options: .atomic)
        return u
    }
}
