import Foundation

/// The booking operations BookingStore needs. The live version calls Django;
/// tests and previews substitute their own.
protocol BookingService {
    func fetchBookings() async throws -> [LabBooking]
    func createBooking(labID: String, start: Date, durationMinutes: Int) async throws -> LabBooking
    func cancelBooking(id: UUID) async throws -> LabBooking
}

struct APIBookingService: BookingService {
    let api: APIClient

    func fetchBookings() async throws -> [LabBooking] {
        try await api.get("bookings/", authenticated: true)
    }

    func createBooking(labID: String, start: Date, durationMinutes: Int) async throws -> LabBooking {
        struct Request: Encodable { let labID: String; let start: Date; let durationMinutes: Int }
        return try await api.post("bookings/",
                                  body: Request(labID: labID, start: start, durationMinutes: durationMinutes),
                                  authenticated: true)
    }

    func cancelBooking(id: UUID) async throws -> LabBooking {
        try await api.post("bookings/\(id.uuidString.lowercased())/cancel/", authenticated: true)
    }
}
