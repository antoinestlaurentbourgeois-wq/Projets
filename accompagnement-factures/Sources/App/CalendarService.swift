import Foundation
import EventKit

/// Lecture directe du calendrier de l'iPhone (EventKit) : aucun export, aucune importation.
@MainActor
final class CalendarService: ObservableObject {
    enum Access { case unknown, granted, denied }

    @Published var access: Access = .unknown
    @Published var calendars: [EKCalendar] = []

    private let ek = EKEventStore()

    init() { refreshStatus() }

    func refreshStatus() {
        switch EKEventStore.authorizationStatus(for: .event) {
        case .fullAccess: access = .granted; reloadCalendars()
        case .denied, .restricted, .writeOnly: access = .denied
        default: access = .unknown
        }
    }

    func requestAccess() async {
        do {
            let ok = try await ek.requestFullAccessToEvents()
            access = ok ? .granted : .denied
            if ok { reloadCalendars() }
        } catch { access = .denied }
    }

    private func reloadCalendars() {
        calendars = ek.calendars(for: .event).sorted { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
    }

    /// Événements entre deux dates, hors calendriers exclus et événements annulés.
    func events(from: Date, to: Date, excluded: [String]) -> [CalEvent] {
        guard access == .granted else { return [] }
        let cal = Fr.cal
        let start = cal.startOfDay(for: from)
        let end = cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: to))!
        let cals = ek.calendars(for: .event).filter { !excluded.contains($0.calendarIdentifier) }
        guard !cals.isEmpty else { return [] }
        let pred = ek.predicateForEvents(withStart: start, end: end, calendars: cals)
        return ek.events(matching: pred).compactMap { e in
            if e.status == .canceled { return nil }
            let id = e.eventIdentifier ?? UUID().uuidString
            return CalEvent(key: id + "|" + String(Int(e.startDate.timeIntervalSince1970)),
                            title: e.title ?? "(sans titre)", location: e.location ?? "",
                            calendar: e.calendar.title, start: e.startDate, end: e.endDate, allDay: e.isAllDay)
        }
    }
}
