import Foundation
import Combine

struct LabBooking: Codable, Identifiable {
    let id: UUID
    let labID: String
    let labName: String
    let start: Date
    let end: Date
}
enum BookingError: LocalizedError {
    case closed, past, overlap
    var errorDescription: String? {
        switch self {
        case .closed: "This lab is currently not accepting reservations."
        case .past: "Please select a future time."
        case .overlap: "This lab already has a reservation during that period."
        }
    }
}
@MainActor
final class BookingStore: ObservableObject {
    @Published private(set) var bookings: [LabBooking] = [] {
        didSet { persist() }
    }
    private let key = "campusos_demo_bookings"
    init() {
        if let data = UserDefaults.standard.data(forKey: key),
           let saved = try? JSONDecoder().decode([LabBooking].self, from: data) {
            bookings = saved
        }
    }
    func reserve(_ lab: Lab, at start: Date) throws {
        guard lab.isOpenForBooking else { throw BookingError.closed }
        guard start > Date() else { throw BookingError.past }
        let end = start.addingTimeInterval(3600)
        guard !bookings.contains(where: {
            $0.labID == lab.id && $0.start < end && start < $0.end
        }) else { throw BookingError.overlap }
        bookings.append(LabBooking(id: UUID(), labID: lab.id,
                                   labName: lab.name, start: start, end: end))
    }
    func cancel(_ booking: LabBooking) {
        bookings.removeAll { $0.id == booking.id }
    }
    private func persist() {
        if let data = try? JSONEncoder().encode(bookings) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}
