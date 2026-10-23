import Foundation

/// Response from POST /api/v1/ai/planner/. Everything except `requirements`
/// comes from CampusOS data; the AI only interpreted the student's text.
struct ProjectPlan: Codable, Equatable {
    let engine: PlannerEngine
    let notes: [String]
    let requirements: PlanRequirements
    let recommendations: [LabRecommendation]
    let missingItems: [MissingItem]
    let nextSteps: [String]
    let disclaimer: String
}

enum PlannerEngine: String, Codable {
    case claude, keywords, other

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = PlannerEngine(rawValue: raw) ?? .other
    }
}

struct PlanRequirements: Codable, Equatable {
    let summary: String
    let teamSize: Int?
    /// Local calendar date, "YYYY-MM-DD".
    let date: String
    let startTime: String?
    let durationMinutes: Int
    let labType: String?
    let items: [PlannedItem]

    var day: Date? { PlanRequirements.dayFormatter.date(from: date) }

    private static let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

struct PlannedItem: Codable, Equatable {
    enum Status: String, Codable {
        case available, unavailable, notInCatalog = "not_in_catalog", other

        init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Status(rawValue: raw) ?? .other
        }
    }

    struct Match: Codable, Equatable {
        let id: String
        let name: String
        let labId: String
        let labName: String
        let isAvailable: Bool
    }

    let name: String
    let quantity: Int?
    let status: Status
    let matches: [Match]
}

struct LabRecommendation: Codable, Equatable, Identifiable {
    struct MatchedEquipment: Codable, Equatable {
        let id: String
        let name: String
        let isAvailable: Bool
    }

    let lab: Lab
    let matchedEquipment: [MatchedEquipment]
    let capacityOk: Bool
    let canBook: Bool
    let blockers: [String]
    let certifications: [PlanCertification]
    let slotsDate: String?
    let suggestedSlots: [PlanSlot]

    var id: String { lab.id }
}

struct PlanCertification: Codable, Equatable {
    let id: String
    let name: String
    /// "certified", "pending", "not_requested", "expired" or "revoked".
    let status: String
    let isValid: Bool
    /// "lab" (needed to book) or "equipment" (needed to use a matched item).
    let requiredFor: String
    let equipment: String?
}

struct PlanSlot: Codable, Equatable, Hashable {
    let start: Date
    let end: Date

    var minutes: Int { Int(end.timeIntervalSince(start) / 60) }
}

struct MissingItem: Codable, Equatable {
    let name: String
    let reason: String
}
