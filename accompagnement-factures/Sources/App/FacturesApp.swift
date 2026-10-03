import SwiftUI

@main
struct FacturesApp: App {
    @StateObject private var store = Store()
    @StateObject private var calendar = CalendarService()
    @StateObject private var router = Router()
    @StateObject private var sender = Sender()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(calendar)
                .environmentObject(router)
                .environmentObject(sender)
                .tint(Color(red: 31 / 255, green: 95 / 255, blue: 91 / 255))
                .task { await start() }
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active { calendar.refreshStatus(); runAutomation() }
                }
                .onChange(of: store.settings.reminder) { _, _ in Reminders.schedule(enabled: store.settings.reminder, day: store.settings.autoDay) }
                .onChange(of: store.settings.autoDay) { _, _ in Reminders.schedule(enabled: store.settings.reminder, day: store.settings.autoDay) }
        }
    }

    private func start() async {
        if calendar.access == .unknown { await calendar.requestAccess() }
        Reminders.schedule(enabled: store.settings.reminder, day: store.settings.autoDay)
        runAutomation()
    }

    /// Crée les brouillons du mois précédent si ce n'est pas déjà fait.
    private func runAutomation() {
        guard calendar.access == .granted else { return }
        let cal = Fr.cal
        let prev = cal.date(byAdding: .month, value: -1, to: Date())!
        let (a, b) = Billing.monthRange(of: prev)
        let events = calendar.events(from: a, to: b, excluded: store.settings.excludedCalendars)
        let n = store.autoDraftIfDue(events: events)
        if n > 0 { router.notice = "\(n) facture\(n > 1 ? "s" : "") du mois dernier \(n > 1 ? "ont" : "a") été préparée\(n > 1 ? "s" : "") en brouillon."; router.tab = .invoices }
    }
}

enum Tab: Hashable { case toBill, invoices, clients, settings }

/// Navigation partagée (onglet affiché, message d'information).
@MainActor
final class Router: ObservableObject {
    @Published var tab: Tab = .toBill
    @Published var notice: String?
}

struct RootView: View {
    @EnvironmentObject var router: Router
    @EnvironmentObject var sender: Sender
    @EnvironmentObject var store: Store

    var body: some View {
        TabView(selection: $router.tab) {
            ToBillView().tabItem { Label("À facturer", systemImage: "calendar.badge.clock") }.tag(Tab.toBill)
            InvoicesView().tabItem { Label("Factures", systemImage: "doc.text") }.tag(Tab.invoices)
            ClientsView().tabItem { Label("Clients", systemImage: "person.2") }.tag(Tab.clients)
            SettingsView().tabItem { Label("Réglages", systemImage: "gearshape") }.tag(Tab.settings)
        }
        .sheet(item: $sender.current) { inv in
            let url = FileStorage.temporaryCopy(inv)
            if MailComposer.canSend {
                MailComposer(recipients: inv.client.recipients,
                             subject: Billing.fill(store.settings.subject, invoice: inv),
                             body: Billing.fill(store.settings.body, invoice: inv),
                             attachment: url) { result in sender.finish(inv, result: result, store: store) }
                    .ignoresSafeArea()
            } else {
                ShareSheet(items: [url, Billing.fill(store.settings.body, invoice: inv)])
                    .onDisappear { sender.finishShared(inv, store: store) }
            }
        }
        .alert("Information", isPresented: Binding(get: { router.notice != nil }, set: { if !$0 { router.notice = nil } })) {
            Button("OK", role: .cancel) {}
        } message: { Text(router.notice ?? "") }
    }
}
