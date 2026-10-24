import Foundation
import Combine

// SafeLab: equipment fault reports (/api/v1/safelab/labs/, /api/v1/safelab/faults/).

struct FaultEquipment: Codable, Identifiable, Hashable {
    /// The asset ID, e.g. "MAC-IMAC-01".
    let id: String
    let name: String
    let type: String
    let isAvailable: Bool
}

struct FaultLab: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let equipment: [FaultEquipment]
}

enum FaultCategory: String, Codable, CaseIterable, Identifiable {
    case notWorking = "not_working", partiallyWorking = "partially_working", physicallyDamaged = "physically_damaged"
    case unexpectedBehaviour = "unexpected_behaviour", other

    var id: String { rawValue }
    var label: String {
        switch self {
        case .notWorking: return "Not Working"
        case .partiallyWorking: return "Partially Working"
        case .physicallyDamaged: return "Physically Damaged"
        case .unexpectedBehaviour: return "Unexpected Behaviour"
        case .other: return "Other Equipment Fault"
        }
    }
}

enum FaultSeverity: String, Codable, CaseIterable, Identifiable {
    case low, medium, high, critical

    var id: String { rawValue }
    var label: String { rawValue.capitalized }
}

struct EquipmentFaultReport: Codable, Identifiable, Equatable {
    enum Status: String, Codable {
        case pending, approved, rejected, underMaintenance = "under_maintenance", resolved, other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Status(rawValue: raw) ?? .other
        }

        var label: String {
            switch self {
            case .pending: return "Pending"
            case .approved: return "Approved"
            case .rejected: return "Rejected"
            case .underMaintenance: return "Under Maintenance"
            case .resolved: return "Resolved"
            case .other: return "Updated"
            }
        }

        /// Faculty actions the server allows from this status.
        var actions: [FaultAction] {
            switch self {
            case .pending: return [.approve, .maintenance, .reject]
            case .approved: return [.maintenance, .resolve]
            case .underMaintenance: return [.resolve]
            default: return []
            }
        }
    }

    let id: Int
    let labId: String
    let labName: String
    let equipmentId: String
    let equipmentName: String
    let equipmentType: String
    let category: String
    let categoryLabel: String
    let severity: String
    let description: String
    let status: Status
    let reporter: String
    let username: String
    let decisionNote: String
    let decidedBy: String?
    let createdAt: Date
    let updatedAt: Date
}

enum FaultAction: String {
    case approve, reject, maintenance, resolve

    var label: String {
        switch self {
        case .approve: return "Approve"
        case .reject: return "Reject"
        case .maintenance: return "Under Maintenance"
        case .resolve: return "Resolved"
        }
    }
}

struct FaultBucket: Codable, Identifiable, Equatable {
    let key: String
    let label: String
    let count: Int

    var id: String { key }
}

/// Chart data computed by the server from the stored reports.
struct FaultAnalytics: Codable, Equatable {
    let byEquipmentType: [FaultBucket]
    let byLab: [FaultBucket]
    let byStatus: [FaultBucket]
    let mostReported: [FaultBucket]
    let monthly: [FaultBucket]
    let total: Int
}

struct FaultSubmission: Encodable, Equatable {
    let labId: String
    let equipmentId: String
    let category: String
    let severity: String
    let description: String
}

protocol EquipmentFaultService {
    func fetchLabs() async throws -> [FaultLab]
    func fetchReports() async throws -> [EquipmentFaultReport]
    func submit(_ report: FaultSubmission) async throws -> EquipmentFaultReport
    func decide(id: Int, action: FaultAction, note: String) async throws -> EquipmentFaultReport
    func fetchAnalytics() async throws -> FaultAnalytics
}

struct APIEquipmentFaultService: EquipmentFaultService {
    let api: APIClient

    func fetchLabs() async throws -> [FaultLab] {
        try await api.get("safelab/labs/", authenticated: true)
    }

    func fetchReports() async throws -> [EquipmentFaultReport] {
        try await api.get("safelab/faults/", authenticated: true)
    }

    func submit(_ report: FaultSubmission) async throws -> EquipmentFaultReport {
        try await api.post("safelab/faults/", body: report, authenticated: true)
    }

    func decide(id: Int, action: FaultAction, note: String) async throws -> EquipmentFaultReport {
        struct Body: Encodable { let note: String }
        return try await api.post("safelab/faults/\(id)/\(action.rawValue)/", body: Body(note: note),
                                  authenticated: true)
    }

    func fetchAnalytics() async throws -> FaultAnalytics {
        try await api.get("safelab/faults/analytics/", authenticated: true)
    }
}

@MainActor
final class EquipmentFaultStore: ObservableObject {
    @Published private(set) var labs: [FaultLab] = []
    @Published private(set) var reports: [EquipmentFaultReport] = []
    @Published private(set) var analytics: FaultAnalytics?
    @Published private(set) var loadState: LoadState = .idle
    @Published private(set) var busyID: Int?

    private let service: EquipmentFaultService

    init(service: EquipmentFaultService) {
        self.service = service
    }

    func load(staff: Bool) async {
        if reports.isEmpty && labs.isEmpty { loadState = .loading }
        do {
            labs = try await service.fetchLabs()
            reports = try await service.fetchReports()
            analytics = staff ? try await service.fetchAnalytics() : nil
            loadState = .loaded
        } catch {
            loadState = .failed(error.localizedDescription)
        }
    }

    /// Equipment of one lab only: a report can't name equipment from elsewhere (the server checks too).
    func equipment(inLab labId: String?) -> [FaultEquipment] {
        labs.first { $0.id == labId }?.equipment ?? []
    }

    @discardableResult
    func submit(labId: String, equipment: FaultEquipment, category: FaultCategory, severity: FaultSeverity,
                description: String) async throws -> EquipmentFaultReport {
        let report = try await service.submit(FaultSubmission(
            labId: labId, equipmentId: equipment.id, category: category.rawValue, severity: severity.rawValue,
            description: description.trimmingCharacters(in: .whitespacesAndNewlines)))
        reports.insert(report, at: 0)
        return report
    }

    func decide(_ report: EquipmentFaultReport, _ action: FaultAction, note: String = "") async throws {
        busyID = report.id
        defer { busyID = nil }
        let updated = try await service.decide(id: report.id, action: action,
                                               note: note.trimmingCharacters(in: .whitespacesAndNewlines))
        if let index = reports.firstIndex(where: { $0.id == updated.id }) {
            reports[index] = updated
        }
        analytics = (try? await service.fetchAnalytics()) ?? analytics
    }

    func reset() {
        labs = []
        reports = []
        analytics = nil
        loadState = .idle
    }
}
