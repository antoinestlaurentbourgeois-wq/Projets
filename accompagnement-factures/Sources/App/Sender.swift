import SwiftUI
import MessageUI

/// File d'envoi : présente un courriel prérempli par facture, l'un après l'autre.
/// iOS n'autorise pas l'envoi silencieux : chaque courriel s'ouvre prêt à envoyer (ou à garder en brouillon).
@MainActor
final class Sender: ObservableObject {
    @Published var current: Invoice?
    private var queue: [Invoice] = []

    func send(_ invoices: [Invoice]) {
        queue = invoices
        next()
    }

    private func next() { current = queue.isEmpty ? nil : queue.removeFirst() }

    func finish(_ inv: Invoice, result: MFMailComposeResult, store: Store) {
        switch result {
        case .sent:
            store.mark(inv, .sent); next()
        case .saved:
            next()            // enregistré comme brouillon dans Mail : la facture reste « Brouillon »
        default:
            queue = []; current = nil
        }
    }

    /// Repli (Outlook, Gmail… sans compte Mail configuré) : la feuille de partage ne dit pas si l'envoi a eu lieu.
    func finishShared(_ inv: Invoice, store: Store) {
        next()
    }
}
