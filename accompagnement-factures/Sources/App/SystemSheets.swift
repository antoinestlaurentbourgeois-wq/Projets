import SwiftUI
import MessageUI
import PDFKit
import UniformTypeIdentifiers

/// Feuille de partage iOS (Courriel, Messages, Fichiers, AirDrop, Outlook…).
struct ShareSheet: UIViewControllerRepresentable {
    var items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

/// Choisir un dossier de l'iPhone ou d'iCloud Drive où copier le PDF.
struct FileExporter: UIViewControllerRepresentable {
    var url: URL
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController { UIDocumentPickerViewController(forExporting: [url], asCopy: true) }
    func updateUIViewController(_ vc: UIDocumentPickerViewController, context: Context) {}
}

/// Courriel prérempli (destinataires, objet, message, PDF joint). L'utilisateur peut envoyer ou enregistrer un brouillon.
struct MailComposer: UIViewControllerRepresentable {
    var recipients: [String]
    var subject: String
    var body: String
    var attachment: URL
    var onResult: (MFMailComposeResult) -> Void

    static var canSend: Bool { MFMailComposeViewController.canSendMail() }

    func makeCoordinator() -> Coordinator { Coordinator(onResult) }

    func makeUIViewController(context: Context) -> MFMailComposeViewController {
        let vc = MFMailComposeViewController()
        vc.mailComposeDelegate = context.coordinator
        vc.setToRecipients(recipients)
        vc.setSubject(subject)
        vc.setMessageBody(body, isHTML: false)
        if let data = try? Data(contentsOf: attachment) {
            vc.addAttachmentData(data, mimeType: "application/pdf", fileName: attachment.lastPathComponent)
        }
        return vc
    }
    func updateUIViewController(_ vc: MFMailComposeViewController, context: Context) {}

    final class Coordinator: NSObject, MFMailComposeViewControllerDelegate {
        let onResult: (MFMailComposeResult) -> Void
        init(_ f: @escaping (MFMailComposeResult) -> Void) { onResult = f }
        func mailComposeController(_ c: MFMailComposeViewController, didFinishWith result: MFMailComposeResult, error: Error?) {
            c.dismiss(animated: true) { self.onResult(result) }
        }
    }
}

/// Aperçu d'un PDF (toutes les pages, zoom).
struct PDFPreview: UIViewRepresentable {
    var data: Data
    func makeUIView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.document = PDFDocument(data: data)
        return v
    }
    func updateUIView(_ v: PDFView, context: Context) { v.document = PDFDocument(data: data) }
}

struct PDFPreviewSheet: View {
    var title: String
    var data: Data
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            PDFPreview(data: data).ignoresSafeArea(edges: .bottom)
                .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fermer") { dismiss() } } }
        }
    }
}
