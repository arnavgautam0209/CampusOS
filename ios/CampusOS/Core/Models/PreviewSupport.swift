#if DEBUG
import SwiftUI

/// In-memory stand-ins so SwiftUI previews never call the real server.
struct PreviewBookingService: BookingService {
    func fetchBookings() async throws -> [LabBooking] { [] }

    func createBooking(labID: String, start: Date, durationMinutes: Int) async throws -> LabBooking {
        LabBooking(id: UUID(), labID: labID, labName: "Preview Lab", start: start,
                   end: start.addingTimeInterval(TimeInterval(durationMinutes * 60)), status: .active)
    }

    func cancelBooking(id: UUID) async throws -> LabBooking {
        throw APIError.notFound("Not available in previews.")
    }
}

struct PreviewSkillPassService: SkillPassService {
    func fetchCatalog() async throws -> [Certification] {
        [Certification(id: "CERT-ELEC-BASIC", name: "Basic Electronics Safety",
                       description: "Safe use of bench power supplies and test equipment.", validityDays: 365)]
    }

    func fetchMyRecords() async throws -> [CertificationRecord] { [] }

    func requestCertification(id: String) async throws -> CertificationRecord {
        throw APIError.notFound("Not available in previews.")
    }
}

extension View {
    @MainActor
    func previewEnvironment() -> some View {
        let api = APIClient(tokenStore: InMemoryTokenStore())
        return environmentObject(AuthManager(api: api))
            .environmentObject(LabStore(fetchLabs: { DemoLabs.all }))
            .environmentObject(BookingStore(service: PreviewBookingService()))
            .environmentObject(SkillPassStore(service: PreviewSkillPassService()))
    }
}
#endif
