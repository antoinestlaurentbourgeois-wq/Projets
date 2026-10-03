import Foundation
import UserNotifications

/// Rappel mensuel : « vos factures sont prêtes ». Planifié sur l'appareil, sans serveur.
enum Reminders {
    static func schedule(enabled: Bool, day: Int) {
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: ["factures-mensuelles"])
        guard enabled else { return }
        center.requestAuthorization(options: [.alert, .sound]) { ok, _ in
            guard ok else { return }
            let content = UNMutableNotificationContent()
            content.title = "Factures du mois"
            content.body = "Les visites du mois dernier sont prêtes : vérifiez et envoyez vos factures."
            content.sound = .default
            var comps = DateComponents(); comps.day = day; comps.hour = 9; comps.minute = 0
            let trigger = UNCalendarNotificationTrigger(dateMatching: comps, repeats: true)
            center.add(UNNotificationRequest(identifier: "factures-mensuelles", content: content, trigger: trigger))
        }
    }
}
