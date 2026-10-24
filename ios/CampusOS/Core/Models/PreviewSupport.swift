#if DEBUG
import SwiftUI

/// In-memory stand-ins so SwiftUI previews never call the real server.
struct PreviewBookingService: BookingService {
    func fetchBookings() async throws -> [LabBooking] { [] }

    func createBooking(labID: String, start: Date, durationMinutes: Int, purpose: String) async throws -> LabBooking {
        LabBooking(id: UUID(), labID: labID, labName: "Preview Lab", start: start,
                   end: start.addingTimeInterval(TimeInterval(durationMinutes * 60)), status: .active)
    }

    func cancelBooking(id: UUID) async throws -> LabBooking {
        throw APIError.notFound("Not available in previews.")
    }

    func fetchPendingReviews() async throws -> [LabBooking] { [] }
    func approve(id: UUID, note: String) async throws -> LabBooking { throw APIError.notFound("Not available in previews.") }
    func decline(id: UUID, note: String) async throws -> LabBooking { throw APIError.notFound("Not available in previews.") }
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

    func fetchPendingReviews() async throws -> [CertificationRecord] { [] }

    func approve(recordID: Int) async throws -> CertificationRecord {
        throw APIError.notFound("Not available in previews.")
    }

    func decline(recordID: Int) async throws -> CertificationRecord {
        throw APIError.notFound("Not available in previews.")
    }
}

struct PreviewAttendanceService: AttendanceService {
    func fetchLive() async throws -> AttendanceLive {
        AttendanceLive(generatedAt: Date(), openSessions: [], readers: [], recentScans: [])
    }

    func fetchMine() async throws -> [MyAttendance] { [] }

    func openSession(classroomId: String, title: String) async throws -> LiveSession {
        throw APIError.notFound("Not available in previews.")
    }

    func closeSession(id: Int) async throws -> LiveSession {
        throw APIError.notFound("Not available in previews.")
    }
}

struct PreviewPlannerService: PlannerService {
    func plan(prompt: String) async throws -> ProjectPlan {
        throw APIError.notFound("Not available in previews.")
    }
}

struct PreviewInventoryService: InventoryService {
    func fetchInventory() async throws -> [InventoryItem] { [] }
    func fetchMyLoans() async throws -> [EquipmentLoan] { [] }
    func fetchAllLoans() async throws -> [EquipmentLoan] { [] }

    func borrow(equipmentId: String, quantity: Int, days: Int) async throws -> EquipmentLoan {
        throw APIError.notFound("Not available in previews.")
    }

    func returnLoan(id: Int, condition: EquipmentLoan.Condition, note: String) async throws -> EquipmentLoan {
        throw APIError.notFound("Not available in previews.")
    }
}

struct PreviewSafeLabService: SafeLabService {
    func fetchDashboard() async throws -> SafetyDashboard {
        SafetyDashboard(generatedAt: Date(), labs: [],
                        thresholds: SafetyThresholds(temperatureC: [:], humidityPct: [:], gasRaw: [:]))
    }

    func acknowledge(alertID: Int) async throws {}
}

struct PreviewSpacesService: SpacesService {
    func fetchAvailability(date: String) async throws -> SpaceAvailability {
        SpaceAvailability(date: date, dayStart: Date(), dayEnd: Date().addingTimeInterval(12 * 3600), rooms: [])
    }

    func fetchMyBookings() async throws -> [RoomBooking] { [] }
    func fetchUtilization() async throws -> [RoomUsage] { [] }

    func book(roomId: String, start: Date, minutes: Int, attendees: Int, purpose: String) async throws -> RoomBooking {
        throw APIError.notFound("Not available in previews.")
    }

    func cancel(id: UUID) async throws -> RoomBooking { throw APIError.notFound("Not available in previews.") }
    func checkIn(id: UUID) async throws -> RoomBooking { throw APIError.notFound("Not available in previews.") }
}

extension View {
    @MainActor
    func previewEnvironment() -> some View {
        let api = APIClient(tokenStore: InMemoryTokenStore())
        return environmentObject(AuthManager(api: api))
            .environmentObject(LabStore(fetchLabs: { DemoLabs.all }))
            .environmentObject(BookingStore(service: PreviewBookingService()))
            .environmentObject(SkillPassStore(service: PreviewSkillPassService()))
            .environmentObject(AttendanceStore(service: PreviewAttendanceService()))
            .environmentObject(PlannerStore(service: PreviewPlannerService()))
            .environmentObject(InventoryStore(service: PreviewInventoryService()))
            .environmentObject(SafeLabStore(service: PreviewSafeLabService()))
            .environmentObject(SpacesStore(service: PreviewSpacesService()))
    }
}
#endif
