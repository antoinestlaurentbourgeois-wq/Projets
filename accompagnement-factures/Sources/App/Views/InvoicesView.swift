import SwiftUI

struct InvoicesView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var sender: Sender
    @State private var filter = 0     // 0 toutes, 1 brouillons, 2 envoyées, 3 payées

    private var shown: [Invoice] {
        store.invoices.filter {
            switch filter {
            case 1: return $0.status == .draft
            case 2: return $0.status == .sent
            case 3: return $0.status == .paid
            default: return true
            }
        }
    }
    private var drafts: [Invoice] { store.invoices.filter { $0.status == .draft && !$0.client.recipients.isEmpty } }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("Filtre", selection: $filter) {
                        Text("Toutes").tag(0); Text("Brouillons").tag(1); Text("Envoyées").tag(2); Text("Payées").tag(3)
                    }.pickerStyle(.segmented)
                }
                if shown.isEmpty {
                    Section { Text("Aucune facture. Créez-les depuis l'onglet « À facturer ».").foregroundStyle(.secondary) }
                }
                ForEach(shown) { inv in
                    NavigationLink { InvoiceDetailView(invoiceID: inv.id) } label: { row(inv) }
                }
                .onDelete { idx in idx.map { shown[$0] }.forEach(store.delete) }
            }
            .navigationTitle("Factures")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { sender.send(drafts) } label: { Label("Envoyer les brouillons", systemImage: "paperplane") }
                        .disabled(drafts.isEmpty)
                }
            }
        }
    }

    private func row(_ inv: Invoice) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(inv.client.name).font(.headline)
                Text("N° \(inv.number) · \(Fr.periode(inv.periodStart, inv.periodEnd))").font(.footnote).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 3) {
                Text(Fr.money(inv.totals.total)).fontWeight(.semibold)
                StatusBadge(status: inv.status)
            }
        }
    }
}

struct StatusBadge: View {
    var status: InvoiceStatus
    var body: some View {
        Text(status.label).font(.caption.weight(.semibold)).padding(.horizontal, 8).padding(.vertical, 2)
            .background(color.opacity(0.15), in: Capsule()).foregroundStyle(color)
    }
    private var color: Color {
        switch status { case .draft: return .orange; case .sent: return .blue; case .paid: return .green }
    }
}

struct InvoiceDetailView: View {
    var invoiceID: UUID
    @EnvironmentObject var store: Store
    @EnvironmentObject var sender: Sender
    @Environment(\.dismiss) private var dismiss

    @State private var preview: Data?
    @State private var exportFile: FileItem?
    @State private var shareFile: FileItem?
    @State private var editing: Invoice?
    @State private var confirmDelete = false

    private var inv: Invoice? { store.invoices.first { $0.id == invoiceID } }

    var body: some View {
        if let inv {
            List {
                Section {
                    LabeledContent("Client", value: inv.client.name)
                    if !inv.client.billTo.isEmpty { LabeledContent("Facturé à", value: inv.client.billTo) }
                    LabeledContent("Période", value: Fr.periode(inv.periodStart, inv.periodEnd))
                    LabeledContent("Échéance", value: Fr.dateLong(inv.due))
                    LabeledContent("Statut") { StatusBadge(status: inv.status) }
                    LabeledContent("Courriel", value: inv.client.recipients.isEmpty ? "—" : inv.client.recipients.joined(separator: ", "))
                }
                Section("Détail") {
                    ForEach(inv.lines) { l in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(l.desc)
                                Text(Fr.dateCourte(l.date) + (l.start != nil ? " · " + Fr.heure(l.start!) : "")).font(.footnote).foregroundStyle(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(Fr.money(l.amount))
                                Text("\(Fr.num(l.qty, l.unit == "h" ? 2 : 0)) \(l.unit) × \(Fr.money(l.rate))").font(.footnote).foregroundStyle(.secondary)
                            }
                        }
                    }
                    LabeledContent("Sous-total", value: Fr.money(inv.totals.subtotal))
                    if inv.taxes.enabled {
                        LabeledContent("TPS", value: Fr.money(inv.totals.tps))
                        LabeledContent("TVQ", value: Fr.money(inv.totals.tvq))
                    }
                    LabeledContent("Total") { Text(Fr.money(inv.totals.total)).fontWeight(.bold) }
                }
                Section {
                    Button { sender.send([inv]) } label: { Label(inv.status == .draft ? "Envoyer par courriel" : "Renvoyer par courriel", systemImage: "envelope") }
                    Button { preview = InvoicePDF.data(for: inv) } label: { Label("Aperçu du PDF", systemImage: "eye") }
                    Button { exportFile = FileItem(url: FileStorage.temporaryCopy(inv)) } label: { Label("Enregistrer dans Fichiers…", systemImage: "folder") }
                    Button { shareFile = FileItem(url: FileStorage.temporaryCopy(inv)) } label: { Label("Partager…", systemImage: "square.and.arrow.up") }
                    Button { editing = inv } label: { Label("Modifier la facture", systemImage: "pencil") }
                } footer: {
                    Text("Copie déjà enregistrée dans Fichiers › Sur mon iPhone › Mes factures › \(String(Fr.cal.component(.year, from: inv.date))) › \(Fr.fileSafe(inv.client.name)).")
                }
                Section {
                    if inv.status != .sent { Button("Marquer comme envoyée") { store.mark(inv, .sent) } }
                    if inv.status != .paid { Button("Marquer comme payée") { store.mark(inv, .paid) } }
                    if inv.status != .draft { Button("Remettre en brouillon") { store.mark(inv, .draft) } }
                    Button("Supprimer la facture", role: .destructive) { confirmDelete = true }
                }
            }
            .navigationTitle("Facture \(inv.number)").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("OK") { dismiss() } } }
            .sheet(isPresented: Binding(get: { preview != nil }, set: { if !$0 { preview = nil } })) {
                PDFPreviewSheet(title: "Facture \(inv.number)", data: preview ?? Data())
            }
            .sheet(item: $exportFile) { FileExporter(url: $0.url) }
            .sheet(item: $shareFile) { ShareSheet(items: [$0.url]) }
            .sheet(item: $editing) { InvoiceEditView(invoice: $0) }
            .confirmationDialog("Supprimer cette facture ?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Supprimer", role: .destructive) { store.delete(inv); dismiss() }
            } message: { Text("Les visites redeviendront disponibles pour une nouvelle facture.") }
        } else {
            Text("Facture introuvable").foregroundStyle(.secondary)
        }
    }
}

struct FileItem: Identifiable { let url: URL; var id: String { url.absoluteString } }

struct InvoiceEditView: View {
    @State var invoice: Invoice
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Facture") {
                    TextField("Numéro", text: $invoice.number)
                    DatePicker("Date", selection: $invoice.date, displayedComponents: .date)
                    DatePicker("Échéance", selection: $invoice.due, displayedComponents: .date)
                }
                Section("Lignes") {
                    ForEach($invoice.lines) { $l in
                        VStack(alignment: .leading, spacing: 6) {
                            TextField("Description", text: $l.desc)
                            HStack {
                                TextField("Qté", value: $l.qty, format: .number).keyboardType(.decimalPad).frame(width: 70)
                                Text(l.unit)
                                Text("×")
                                TextField("Taux", value: $l.rate, format: .number).keyboardType(.decimalPad).frame(width: 80)
                                Spacer()
                                Text(Fr.money(l.amount)).foregroundStyle(.secondary)
                            }
                        }
                    }
                    .onDelete { invoice.lines.remove(atOffsets: $0) }
                    Button("Ajouter une ligne") {
                        invoice.lines.append(InvoiceLine(date: invoice.date, desc: "", qty: 1, unit: "h", rate: invoice.client.rate))
                    }
                }
                Section("Notes (affichées sur la facture)") {
                    TextEditor(text: $invoice.notes).frame(minHeight: 70)
                }
            }
            .navigationTitle("Modifier").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Annuler") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Enregistrer") { store.update(invoice); dismiss() } }
            }
        }
    }
}
