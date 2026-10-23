import Foundation
import Combine

struct LabBooking: Identifiable, Codable {
    let id: UUID
    let labID: String
    let labName: String
    let start: Date
    let end: Date
}

enum BookingFailure: Error, LocalizedError {
    case closed, past, conflict, invalidDuration

    var errorDescription: String? {
        switch self {
        case .closed: return "This lab is not accepting bookings."
        case .past: return "Choose a future start time."
        case .conflict: return "This lab already has an overlapping reservation."
        case .invalidDuration: return "The booking duration must be positive."
        }
    }
}

@MainActor
final class BookingStore: ObservableObject {
    @Published private(set) var bookings: [LabBooking] = [] {
        didSet { save() }
    }

    private let storageKey = "campusos_demo_lab_bookings_v1"
    private let defaults: UserDefaults
    private let now: () -> Date

    // Tests inject an isolated UserDefaults suite and a fixed clock.
    init(defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init) {
        self.defaults = defaults
        self.now = now
        if let data = defaults.data(forKey: storageKey),
           let saved = try? JSONDecoder().decode([LabBooking].self, from: data) {
            bookings = saved
        }
    }

    func reserve(lab: Lab, start: Date, durationMinutes: Int = 60) throws {
        guard lab.isOpenForBooking else { throw BookingFailure.closed }
        guard durationMinutes > 0 else { throw BookingFailure.invalidDuration }
        guard start > now() else { throw BookingFailure.past }
        let end = start.addingTimeInterval(TimeInterval(durationMinutes * 60))
        let overlaps = bookings.contains {
            $0.labID == lab.id && $0.start < end && start < $0.end
        }
        guard !overlaps else { throw BookingFailure.conflict }
        bookings.append(LabBooking(id: UUID(), labID: lab.id,
                                   labName: lab.name, start: start, end: end))
    }

    func cancel(_ booking: LabBooking) {
        bookings.removeAll { $0.id == booking.id }
    }

    private func save() {
        if let data = try? JSONEncoder().encode(bookings) {
            defaults.set(data, forKey: storageKey)
        }
    }
}
